"""AI assistant: natural-language question -> validated read-only SQL -> answer.

Pipeline for each question:
  1. The LLM translates the question into one PostgreSQL SELECT (JSON output).
  2. `sql_guard.prepare_select` validates it structurally (single SELECT, app
     tables only, allowlisted functions) and re-renders it for the live DB.
  3. It runs in a read-only transaction with a statement timeout and a row cap.
  4. If validation or execution fails, the error goes back to the LLM for one
     self-correction attempt.
  5. The LLM phrases the rows as a short answer.

Without an LLM (none configured, or the provider is down / rate-limited), a
small library of built-in report queries answers the four required questions
with deterministic summaries.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import settings
from .llm import LLMClient, LLMError
from .sql_guard import UnsafeSQLError, prepare_select

log = logging.getLogger(__name__)

MAX_ROWS = 200
STATEMENT_TIMEOUT_MS = 5000
MAX_SQL_ATTEMPTS = 2

SCHEMA_DESCRIPTION = """
Tables (PostgreSQL):
  categories(id, code, name)          -- code is one of 'General','OBC','SC','ST'
  students(id, roll_no, name, marks, category_id -> categories.id, application_date)
  courses(id, name, total_seats)
  course_quotas(id, course_id -> courses.id, category_id -> categories.id, reserved_seats)
  preferences(id, student_id -> students.id, course_id -> courses.id, priority)  -- priority 1..3
  allocations(id, student_id -> students.id, course_id -> courses.id,
              seat_type, preference_rank, allocated_at)  -- seat_type is 'open' or 'reserved'
Notes:
  - marks are 0..100; higher marks = higher merit.
  - allocations has at most one row per student (the course they were allocated).
  - preference_rank is which of the student's preferences they got (1 = first choice).
  - A student "did not receive their first preference" if their allocation's
    preference_rank > 1, or they have no allocation row at all.
  - open seats of a course = total_seats - sum(course_quotas.reserved_seats).
  - applicants of a course = distinct students listing it in preferences.
"""

SQL_SYSTEM_PROMPT = f"""You translate questions about a university course-allocation \
database into ONE read-only PostgreSQL SELECT query.

Respond with JSON only: {{"sql": "<query>"}}.
Rules:
- A single SELECT (CTEs allowed). Never modify data. Use only the tables below.
- Return human-readable columns (student/course names, category codes), not bare ids.
- Include the numbers that support the answer (counts, rates, marks) as columns.
- Give computed columns short snake_case aliases.
- Add LIMIT 100 unless the question asks for a single aggregate.
- If the question cannot be answered from this schema, respond {{"sql": ""}}.
{SCHEMA_DESCRIPTION}"""

SUMMARY_SYSTEM_PROMPT = (
    "You answer questions about a university course-allocation system. Using ONLY "
    "the JSON rows provided (the result of a database query), answer the question "
    "in 1-3 plain sentences. Mention concrete names and numbers. Do not mention SQL, "
    "queries, or JSON."
)


# --------------------------------------------------------------------------- #
# Query execution
# --------------------------------------------------------------------------- #
def _jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def run_readonly_query(db: Session, sql: str) -> tuple[list[str], list[dict], bool]:
    """Execute a validated SELECT read-only. Returns (columns, rows, truncated)."""
    dialect = db.get_bind().dialect.name
    db.rollback()  # start from a fresh transaction so the read-only setting applies to it
    conn = db.connection()  # pin one connection for the settings, the query and the reset
    try:
        if dialect == "postgresql":
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}"))
        elif dialect == "sqlite":
            conn.exec_driver_sql("PRAGMA query_only = ON")
        result = conn.execute(text(sql))
        columns = list(result.keys())
        fetched = result.fetchmany(MAX_ROWS + 1)
    finally:
        if dialect == "sqlite":
            # query_only is per-connection, not per-transaction: reset it before
            # the connection goes back to the pool.
            conn.exec_driver_sql("PRAGMA query_only = OFF")
        db.rollback()
    truncated = len(fetched) > MAX_ROWS
    rows = [
        {col: _jsonable(val) for col, val in zip(columns, row, strict=True)}
        for row in fetched[:MAX_ROWS]
    ]
    return columns, rows, truncated


def _target_dialect(db: Session) -> str:
    name = db.get_bind().dialect.name
    return "postgres" if name == "postgresql" else name


# --------------------------------------------------------------------------- #
# Built-in reports (no LLM required)
# --------------------------------------------------------------------------- #
def _pct(x) -> str:
    return f"{float(x) * 100:.1f}%"


def _summarize_per_course(rows: list[dict]) -> str:
    if not rows:
        return "There are no courses yet."
    total = sum(r["allocated"] for r in rows)
    top, low = rows[0], rows[-1]
    return (
        f"{total} students are allocated across {len(rows)} courses. "
        f"{top['course']} has the most ({top['allocated']}) and "
        f"{low['course']} the fewest ({low['allocated']})."
    )


def _summarize_not_first(rows: list[dict]) -> str:
    if not rows:
        return "Every student received their first preference."
    unplaced = sum(1 for r in rows if r["allocated_course"] is None)
    lower = len(rows) - unplaced
    return (
        f"{len(rows)} students did not receive their first preference: "
        f"{lower} were placed in a lower preference and {unplaced} were not allocated."
    )


def _summarize_rejection(rows: list[dict]) -> str:
    rows = [r for r in rows if r["applicants"]]
    if not rows:
        return "No course has any applicants yet."
    top = rows[0]
    rejected = top["applicants"] - top["allocated"]
    return (
        f"{top['course']} has the highest rejection rate at {_pct(top['rejection_rate'])}: "
        f"{rejected} of its {top['applicants']} applicants were not allocated to it."
    )


def _summarize_category(rows: list[dict]) -> str:
    if not rows:
        return "No categories found."
    parts = ", ".join(f"{r['category']} {r['allocated']}" for r in rows)
    return f"Allocated students by category: {parts}."


# (intent pattern, report title, PostgreSQL query, deterministic summarizer)
FALLBACK_QUERIES: list[tuple[re.Pattern, str, str, Callable[[list[dict]], str]]] = [
    (
        re.compile(r"how many.*each course|allocated to each course|per course|by course", re.I),
        "Students allocated per course",
        """SELECT c.name AS course, COUNT(a.id) AS allocated
           FROM courses c LEFT JOIN allocations a ON a.course_id = c.id
           GROUP BY c.name ORDER BY allocated DESC, course""",
        _summarize_per_course,
    ),
    (
        re.compile(r"first (preference|choice)|not.*first|didn'?t get", re.I),
        "Students who did not receive their first preference",
        """SELECT s.roll_no, s.name, c.name AS allocated_course, a.preference_rank
           FROM students s
           LEFT JOIN allocations a ON a.student_id = s.id
           LEFT JOIN courses c ON c.id = a.course_id
           WHERE a.id IS NULL OR a.preference_rank > 1
           ORDER BY s.name""",
        _summarize_not_first,
    ),
    (
        re.compile(r"highest rejection|rejection rate|most rejection|most rejected", re.I),
        "Course rejection rates",
        # Must stay identical to the dashboard's definition
        # (app/routers/dashboard.py): (applicants - allocated) / applicants,
        # rounded to 4 dp, and 0 (not NULL) when there are no applicants.
        """SELECT c.name AS course,
                  COUNT(DISTINCT p.student_id) AS applicants,
                  COUNT(DISTINCT a.student_id) AS allocated,
                  ROUND(COALESCE(
                      (COUNT(DISTINCT p.student_id) - COUNT(DISTINCT a.student_id)) * 1.0
                      / NULLIF(COUNT(DISTINCT p.student_id), 0), 0), 4) AS rejection_rate
           FROM courses c
           LEFT JOIN preferences p ON p.course_id = c.id
           LEFT JOIN allocations a ON a.course_id = c.id AND a.student_id = p.student_id
           GROUP BY c.name ORDER BY rejection_rate DESC, applicants DESC""",
        _summarize_rejection,
    ),
    (
        re.compile(r"category.*allocation|category-wise|by category|category summary", re.I),
        "Category-wise allocation summary",
        """SELECT cat.code AS category, COUNT(a.id) AS allocated
           FROM categories cat
           LEFT JOIN students s ON s.category_id = cat.id
           LEFT JOIN allocations a ON a.student_id = s.id
           GROUP BY cat.code ORDER BY allocated DESC, category""",
        _summarize_category,
    ),
]

_HELP_TEXT = (
    "Try one of the built-in reports: 'How many students were allocated to each "
    "course?', 'Which students did not receive their first preference?', 'Which "
    "course had the highest rejection rate?', or 'Category-wise allocation summary'."
)


def _answer_with_fallback(db: Session, question: str, reason: str) -> dict:
    for pattern, title, sql, summarize in FALLBACK_QUERIES:
        if pattern.search(question):
            safe_sql = prepare_select(sql, target=_target_dialect(db))
            columns, rows, truncated = run_readonly_query(db, safe_sql)
            return {
                "sql": safe_sql,
                "columns": columns,
                "rows": rows,
                "truncated": truncated,
                "answer": f"{title}: {summarize(rows)}",
                "source": "fallback",
            }
    return {
        "sql": None,
        "columns": [],
        "rows": [],
        "truncated": False,
        "answer": f"{reason} {_HELP_TEXT}",
        "source": "none",
    }


# --------------------------------------------------------------------------- #
# LLM path
# --------------------------------------------------------------------------- #
class _NoValidQuery(Exception):
    pass


def _extract_sql(raw: str) -> str:
    """Pull the SQL out of a model response: JSON {"sql": ...}, a fenced block, or prose."""
    raw = raw.strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and isinstance(data.get("sql"), str):
            return data["sql"].strip()
    except ValueError:
        pass
    fence = re.search(r"```(?:sql|json)?\s*(.*?)```", raw, re.S | re.I)
    candidate = fence.group(1) if fence else raw
    m = re.search(r"\b(with|select)\b.*", candidate, re.S | re.I)
    return (m.group(0) if m else candidate).strip()


def _plain_summary(rows: list[dict], truncated: bool) -> str:
    if not rows:
        return "No matching records found."
    preview = "; ".join(", ".join(f"{k}: {v}" for k, v in row.items()) for row in rows[:5])
    more = len(rows) - 5
    suffix = f" (+{more} more{', list truncated' if truncated else ''})" if more > 0 else ""
    return f"{preview}{suffix}"


class _Budget:
    """Wall-clock budget shared by all LLM calls for one answer."""

    MIN_CALL_SECONDS = 3.0

    def __init__(self, seconds: float) -> None:
        self._deadline = time.monotonic() + seconds

    def call_timeout(self) -> float:
        """Timeout for the next LLM call; raises LLMError once the budget is spent."""
        remaining = self._deadline - time.monotonic()
        if remaining < self.MIN_CALL_SECONDS:
            raise LLMError("assistant time budget exhausted")
        return min(settings.llm_timeout_seconds, remaining)


def _summarize_with_llm(
    llm: LLMClient, question: str, rows: list[dict], truncated: bool, budget: _Budget
) -> str:
    if not rows:
        return "No matching records found."
    payload = json.dumps(rows[:50], default=str)
    partial = truncated or len(rows) > 50
    note = (
        "\nThese are only the first rows; more exist, so say the list is partial."
        if partial
        else ""
    )
    try:
        answer = llm.generate(
            f"Question: {question}\nRows: {payload}{note}",
            system=SUMMARY_SYSTEM_PROMPT,
            timeout=budget.call_timeout(),
        ).strip()
        return answer or _plain_summary(rows, truncated)
    except LLMError as e:
        log.warning("LLM summary failed, using plain summary: %s", e)
        return _plain_summary(rows, truncated)


def _answer_with_llm(db: Session, question: str, llm: LLMClient) -> dict:
    target = _target_dialect(db)
    budget = _Budget(settings.assistant_time_budget_seconds)
    prompt = f"Question: {question}"
    for attempt in range(1, MAX_SQL_ATTEMPTS + 1):
        raw = llm.generate(
            prompt, system=SQL_SYSTEM_PROMPT, json_mode=True, timeout=budget.call_timeout()
        )
        sql = _extract_sql(raw)
        if not sql:
            return {
                "sql": None,
                "columns": [],
                "rows": [],
                "truncated": False,
                "answer": "I can only answer questions about students, courses, seat quotas, "
                "preferences and allocations. " + _HELP_TEXT,
                "source": "llm",
            }
        try:
            safe_sql = prepare_select(sql, target=target)
            columns, rows, truncated = run_readonly_query(db, safe_sql)
        except UnsafeSQLError as e:
            log.info("LLM SQL rejected (attempt %d): %s", attempt, e)
            problem = f"was rejected by the safety check: {e}"
        except SQLAlchemyError as e:
            log.info("LLM SQL failed (attempt %d): %s", attempt, e.__class__.__name__)
            detail = str(getattr(e, "orig", e)).splitlines()[0][:300]
            problem = f"failed to execute: {detail}"
        else:
            return {
                "sql": safe_sql,
                "columns": columns,
                "rows": rows,
                "truncated": truncated,
                "answer": _summarize_with_llm(llm, question, rows, truncated, budget),
                "source": "llm",
            }
        prompt = (
            f"Question: {question}\n\nYour previous query:\n{sql}\n{problem}\n"
            "Return a corrected query."
        )
    raise _NoValidQuery


def answer_question(db: Session, question: str, llm: LLMClient | None) -> dict:
    """Answer a natural-language question.

    Returns a dict with keys: sql, columns, rows, truncated, answer, source
    ('llm' | 'fallback' | 'none').
    """
    if llm is None:
        return _answer_with_fallback(db, question, "No LLM is configured.")
    try:
        return _answer_with_llm(db, question, llm)
    except LLMError as e:
        log.warning("LLM unavailable, falling back to built-in reports: %s", e)
        return _answer_with_fallback(db, question, "The language model is unavailable right now.")
    except _NoValidQuery:
        return _answer_with_fallback(
            db, question, "I couldn't turn that question into a safe database query."
        )
