"""AI assistant: LLM path (with a scripted fake model), self-correction,
fallback reports, read-only execution, and the Gemini/Ollama HTTP clients."""

from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.ai_assistant import FALLBACK_QUERIES, _extract_sql, run_readonly_query
from app.config import settings
from app.database import SessionLocal
from app.llm import GeminiClient, LLMError, OllamaClient, get_llm
from app.main import app
from app.routers.assistant import assistant_limiter
from app.sql_guard import prepare_select


class FakeLLM:
    """Returns scripted responses in order and records every prompt."""

    provider, model = "fake", "fake-1"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.prompts: list[tuple[str, str, bool]] = []
        self.timeouts: list[float | None] = []

    def generate(self, prompt, *, system, json_mode=False, timeout=None):
        self.prompts.append((prompt, system, json_mode))
        self.timeouts.append(timeout)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def seeded(client, admin_headers):
    """Two courses, four students, allocation run."""
    cs = client.post(
        "/courses", json={"name": "CS", "total_seats": 1}, headers=admin_headers
    ).json()
    ee = client.post(
        "/courses", json={"name": "EE", "total_seats": 2}, headers=admin_headers
    ).json()
    for roll, marks, prefs in [
        ("S1", 95, [cs, ee]),
        ("S2", 85, [cs, ee]),
        ("S3", 75, [cs]),
        ("S4", 65, [ee]),
    ]:
        client.post(
            "/students",
            json={
                "roll_no": roll,
                "name": f"Student {roll}",
                "marks": marks,
                "category_code": "General",
                "preferences": [
                    {"course_id": c["id"], "priority": i} for i, c in enumerate(prefs, 1)
                ],
            },
            headers=admin_headers,
        )
    client.post("/allocation/run", headers=admin_headers)


def ask(client, headers, question, llm=None):
    app.dependency_overrides[get_llm] = lambda: llm
    return client.post("/assistant/query", json={"question": question}, headers=headers)


def sql_json(sql):
    return json.dumps({"sql": sql})


# ------------------------------------------------------------- LLM path ----
def test_llm_answers_with_validated_sql(client, viewer_headers, seeded):
    llm = FakeLLM(
        sql_json("SELECT name, marks FROM students WHERE marks > 80 ORDER BY marks DESC"),
        "Student S1 (95) and Student S2 (85) scored above 80.",
    )
    res = ask(client, viewer_headers, "Who scored above 80?", llm)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source"] == "llm"
    assert body["columns"] == ["name", "marks"]
    assert body["rows"] == [
        {"name": "Student S1", "marks": 95.0},
        {"name": "Student S2", "marks": 85.0},
    ]
    assert body["answer"].startswith("Student S1")
    assert llm.prompts[0][2] is True  # SQL generation requests JSON output
    assert "Student S1" in llm.prompts[1][0]  # summary sees the rows


def test_llm_self_corrects_after_unsafe_sql(client, viewer_headers, seeded):
    llm = FakeLLM(
        sql_json("SELECT pg_read_file('/etc/passwd')"),
        sql_json("SELECT COUNT(*) AS n FROM students"),
        "There are 4 students.",
    )
    body = ask(client, viewer_headers, "How many students?", llm).json()
    assert body["source"] == "llm"
    assert body["rows"] == [{"n": 4}]
    assert "rejected by the safety check" in llm.prompts[1][0]


def test_llm_self_corrects_after_sql_error(client, viewer_headers, seeded):
    llm = FakeLLM(
        sql_json("SELECT no_such_column FROM students"),
        sql_json("SELECT COUNT(*) AS n FROM courses"),
        "There are 2 courses.",
    )
    body = ask(client, viewer_headers, "How many courses?", llm).json()
    assert body["rows"] == [{"n": 2}]
    assert "failed to execute" in llm.prompts[1][0]


def test_persistently_unsafe_llm_falls_back_to_builtin_report(client, viewer_headers, seeded):
    llm = FakeLLM(sql_json("DELETE FROM students"), sql_json("DROP TABLE students"))
    body = ask(client, viewer_headers, "Category-wise allocation summary please", llm).json()
    assert body["source"] == "fallback"
    assert client.get("/students", headers=viewer_headers).headers["X-Total-Count"] == "4"


def test_llm_outage_falls_back_to_builtin_report(client, viewer_headers, seeded):
    llm = FakeLLM(LLMError("Gemini rate limit reached"))
    body = ask(client, viewer_headers, "Which course had the highest rejection rate?", llm).json()
    assert body["source"] == "fallback"
    assert body["answer"].startswith("Course rejection rates: CS has the highest rejection rate")


def test_summary_failure_degrades_to_plain_text(client, viewer_headers, seeded):
    llm = FakeLLM(sql_json("SELECT COUNT(*) AS n FROM students"), LLMError("timeout"))
    body = ask(client, viewer_headers, "How many students?", llm).json()
    assert body["source"] == "llm"
    assert body["answer"] == "n: 4"


def test_llm_calls_share_a_time_budget(client, viewer_headers, seeded, monkeypatch):
    monkeypatch.setattr(settings, "assistant_time_budget_seconds", 10.0)
    monkeypatch.setattr(settings, "llm_timeout_seconds", 8.0)
    llm = FakeLLM(sql_json("SELECT COUNT(*) AS n FROM students"), "There are 4 students.")
    ask(client, viewer_headers, "How many students?", llm)
    assert llm.timeouts[0] == 8.0  # capped by the per-call timeout
    assert 0 < llm.timeouts[1] <= 8.0


def test_exhausted_budget_falls_back_without_calling_the_llm(
    client, viewer_headers, seeded, monkeypatch
):
    monkeypatch.setattr(settings, "assistant_time_budget_seconds", 1.0)  # < minimum per call
    llm = FakeLLM()
    body = ask(client, viewer_headers, "Category-wise allocation summary", llm).json()
    assert body["source"] == "fallback"
    assert llm.prompts == []


def test_unanswerable_question(client, viewer_headers, seeded):
    body = ask(client, viewer_headers, "What's the weather?", FakeLLM(sql_json(""))).json()
    assert body["sql"] is None
    assert "only answer questions" in body["answer"]


# --------------------------------------------------------- fallback path ----
@pytest.mark.parametrize(
    "question,expected",
    [
        (
            "How many students were allocated to each course?",
            "Students allocated per course: "
            "3 students are allocated across 2 courses. EE has the most (2) and CS the fewest (1).",
        ),
        (
            "Which students did not receive their first preference?",
            "Students who did not receive "
            "their first preference: 2 students did not receive their first preference: 1 were "
            "placed in a lower preference and 1 were not allocated.",
        ),
        (
            "Which course had the highest rejection rate?",
            "Course rejection rates: CS has the "
            "highest rejection rate at 66.7%: 2 of its 3 applicants were not allocated to it.",
        ),
        (
            "Give me a category-wise allocation summary.",
            "Category-wise allocation summary: "
            "Allocated students by category: General 3, OBC 0, SC 0, ST 0.",
        ),
    ],
)
def test_builtin_reports_without_llm(client, viewer_headers, seeded, question, expected):
    body = ask(client, viewer_headers, question, None).json()
    assert body["source"] == "fallback"
    assert body["answer"] == expected
    assert body["sql"]


def test_no_llm_and_no_matching_report(client, viewer_headers, seeded):
    body = ask(client, viewer_headers, "Tell me a joke", None).json()
    assert body["source"] == "none"
    assert "No LLM is configured" in body["answer"]


def test_all_fallback_queries_pass_the_guard():
    for _, _, sql, _ in FALLBACK_QUERIES:
        assert prepare_select(sql)


def test_assistant_rate_limited_per_user(client, viewer_headers, monkeypatch):
    monkeypatch.setattr(assistant_limiter, "limit", 2)
    for _ in range(2):
        assert ask(client, viewer_headers, "category-wise summary").status_code == 200
    assert ask(client, viewer_headers, "category-wise summary").status_code == 429


def test_question_length_validated(client, viewer_headers):
    assert ask(client, viewer_headers, "x" * 501).status_code == 422
    assert ask(client, viewer_headers, "  ").status_code == 422


# ----------------------------------------------------- read-only execution ----
def test_execution_layer_is_read_only_even_if_guard_were_bypassed(seeded):
    with SessionLocal() as db:
        with pytest.raises(DBAPIError):  # SQLite: OperationalError; Postgres: InternalError
            run_readonly_query(db, "DELETE FROM students")
        # The session is still usable and nothing was deleted.
        assert db.execute(text("SELECT COUNT(*) FROM students")).scalar() == 4


def test_row_cap_marks_results_truncated(seeded, monkeypatch):
    monkeypatch.setattr("app.ai_assistant.MAX_ROWS", 2)
    with SessionLocal() as db:
        columns, rows, truncated = run_readonly_query(db, "SELECT roll_no FROM students")
    assert columns == ["roll_no"] and len(rows) == 2 and truncated


# ------------------------------------------------------------ extraction ----
@pytest.mark.parametrize(
    "raw,expected",
    [
        ('{"sql": "SELECT 1"}', "SELECT 1"),
        ("Sure:\n```sql\nSELECT * FROM students;\n```", "SELECT * FROM students;"),
        ("The answer is: SELECT count(*) FROM students", "SELECT count(*) FROM students"),
    ],
)
def test_extract_sql(raw, expected):
    assert _extract_sql(raw) == expected


# ---------------------------------------------------------- HTTP clients ----
def _gemini(handler):
    return GeminiClient(
        "test-key", "gemini-test", http=httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_gemini_client_request_and_response_parsing():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers["x-goog-api-key"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "thinking...", "thought": True},
                                {"text": '{"sql": "SELECT 1"}'},
                            ]
                        }
                    }
                ]
            },
        )

    out = _gemini(handler).generate("q", system="sys", json_mode=True)
    assert out == '{"sql": "SELECT 1"}'  # thought parts skipped
    assert seen["url"].endswith("/models/gemini-test:generateContent")
    assert seen["key"] == "test-key"
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert seen["body"]["systemInstruction"]["parts"][0]["text"] == "sys"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(429, json={}),
        httpx.Response(500, text="boom"),
        httpx.Response(200, json={"candidates": []}),
        httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": " "}]}}]}),
    ],
)
def test_gemini_client_errors_become_llm_errors(response):
    with pytest.raises(LLMError):
        _gemini(lambda request: response).generate("q", system="s")


def test_gemini_network_error_becomes_llm_error():
    def handler(request):
        raise httpx.ConnectError("down")

    with pytest.raises(LLMError):
        _gemini(handler).generate("q", system="s")


def test_ollama_client():
    def handler(request):
        body = json.loads(request.content)
        assert body["format"] == "json" and body["model"] == "llama3.1"
        return httpx.Response(200, json={"response": '{"sql": "SELECT 1"}'})

    client = OllamaClient(
        "http://ollama:11434/",
        "llama3.1",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert client.generate("q", system="s", json_mode=True) == '{"sql": "SELECT 1"}'
