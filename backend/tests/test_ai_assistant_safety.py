"""Unit tests for the AI assistant's SQL safety gate and fallback library."""
from app.ai_assistant import FALLBACK_QUERIES, _extract_sql, _is_safe_select


def test_accepts_plain_select():
    assert _is_safe_select("SELECT * FROM students;")


def test_accepts_cte_with_statement():
    assert _is_safe_select("WITH t AS (SELECT 1) SELECT * FROM t")


def test_rejects_write_statements():
    for stmt in [
        "DELETE FROM students",
        "UPDATE students SET marks = 100",
        "DROP TABLE students",
        "INSERT INTO students (name) VALUES ('x')",
        "TRUNCATE students",
        "ALTER TABLE students ADD COLUMN x int",
    ]:
        assert not _is_safe_select(stmt), stmt


def test_rejects_non_select_start():
    assert not _is_safe_select("EXPLAIN SELECT * FROM students")


def test_rejects_multiple_statements():
    assert not _is_safe_select("SELECT 1; DROP TABLE students;")


def test_rejects_write_hidden_inside_select_text():
    # Even embedded as a substring/comment, a forbidden keyword blocks the query.
    assert not _is_safe_select("SELECT * FROM students; UPDATE students SET marks=0")


def test_extract_sql_pulls_query_out_of_markdown_fence():
    raw = "Sure, here you go:\n```sql\nSELECT * FROM students;\n```"
    assert _extract_sql(raw) == "SELECT * FROM students;"


def test_extract_sql_trims_leading_prose():
    raw = "The answer is: SELECT count(*) FROM students"
    assert _extract_sql(raw).lower().startswith("select")


def test_fallback_queries_cover_the_four_required_report_questions():
    required_questions = [
        "How many students were allocated to each course?",
        "Which students did not receive their first preference?",
        "Which course had the highest rejection rate?",
        "Give me a category-wise allocation summary.",
    ]
    for question in required_questions:
        matched = [label for pattern, label, _ in FALLBACK_QUERIES if pattern.search(question)]
        assert matched, f"no fallback query matches: {question!r}"


def test_all_fallback_queries_are_safe_selects():
    for _, _, sql in FALLBACK_QUERIES:
        assert _is_safe_select(sql), sql
