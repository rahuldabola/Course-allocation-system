"""API-level tests: validation, CRUD, the allocation endpoint end-to-end,
dashboard aggregation, history and export."""

from __future__ import annotations

import csv
import io

import pytest


@pytest.fixture
def api(client, admin_headers):
    """Small helper bound to an admin session."""

    class Api:
        headers = admin_headers

        def course(self, name="Computer Science", total_seats=2, quotas=None):
            res = client.post(
                "/courses",
                json={"name": name, "total_seats": total_seats, "quotas": quotas or []},
                headers=admin_headers,
            )
            assert res.status_code == 201, res.text
            return res.json()

        def student(self, roll_no, marks, category_code, course_ids, **extra):
            if isinstance(course_ids, int):
                course_ids = [course_ids]
            payload = {
                "roll_no": roll_no,
                "name": extra.pop("name", f"Student {roll_no}"),
                "marks": marks,
                "category_code": category_code,
                "preferences": [
                    {"course_id": cid, "priority": i} for i, cid in enumerate(course_ids, start=1)
                ],
                **extra,
            }
            res = client.post("/students", json=payload, headers=admin_headers)
            assert res.status_code == 201, res.text
            return res.json()

        def get(self, path, **kw):
            return client.get(path, headers=admin_headers, **kw)

        def post(self, path, **kw):
            return client.post(path, headers={**admin_headers, **kw.pop("headers", {})}, **kw)

        def put(self, path, **kw):
            return client.put(path, headers=admin_headers, **kw)

        def delete(self, path):
            return client.delete(path, headers=admin_headers)

    return Api()


# ---------------------------------------------------------------- meta ----
def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "database": "ok"}


def test_meta_is_public_and_hides_demo_accounts_outside_demo_mode(client):
    body = client.get("/meta").json()
    assert body["demo_mode"] is False
    assert body["demo_accounts"] == []
    assert body["llm_provider"] == "none"


def test_reset_demo_unavailable_outside_demo_mode(api):
    assert api.post("/admin/reset-demo").status_code == 404


# ------------------------------------------------------------- courses ----
def test_create_and_list_course(api):
    course = api.course(quotas=[{"category_code": "SC", "reserved_seats": 1}])
    assert course["open_seats"] == 1
    assert course["applicants"] == 0
    assert course["quotas"] == [{"category_code": "SC", "reserved_seats": 1}]
    assert api.get("/courses").json()[0]["name"] == "Computer Science"
    assert api.get(f"/courses/{course['id']}").json()["id"] == course["id"]


def test_duplicate_course_name_conflicts_case_insensitively(api):
    api.course()
    res = api.post("/courses", json={"name": "computer science", "total_seats": 5})
    assert res.status_code == 409


def test_reserved_seats_exceeding_total_seats_rejected(api):
    res = api.post(
        "/courses",
        json={
            "name": "X",
            "total_seats": 1,
            "quotas": [{"category_code": "SC", "reserved_seats": 2}],
        },
    )
    assert res.status_code == 400


def test_quota_for_general_category_rejected(api):
    res = api.post(
        "/courses",
        json={
            "name": "X",
            "total_seats": 5,
            "quotas": [{"category_code": "General", "reserved_seats": 1}],
        },
    )
    assert res.status_code == 422


def test_update_course_renaming_onto_existing_name_conflicts(api):
    # Regression: this used to hit the DB unique constraint and return 500.
    api.course("A")
    b = api.course("B")
    assert api.put(f"/courses/{b['id']}", json={"name": "A"}).status_code == 409


def test_update_course_cannot_shrink_seats_below_reserved(api):
    # Regression: lowering total_seats without resending quotas skipped validation.
    course = api.course(total_seats=5, quotas=[{"category_code": "OBC", "reserved_seats": 3}])
    res = api.put(f"/courses/{course['id']}", json={"total_seats": 2})
    assert res.status_code == 400
    assert api.get(f"/courses/{course['id']}").json()["total_seats"] == 5


def test_update_course_replaces_quotas(api):
    course = api.course(total_seats=6, quotas=[{"category_code": "OBC", "reserved_seats": 2}])
    res = api.put(
        f"/courses/{course['id']}",
        json={"total_seats": 8, "quotas": [{"category_code": "SC", "reserved_seats": 3}]},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["quotas"] == [{"category_code": "SC", "reserved_seats": 3}]
    assert body["open_seats"] == 5


def test_delete_course_refused_while_referenced(api):
    course = api.course()
    student = api.student("R1", 90, "General", course["id"])
    assert api.delete(f"/courses/{course['id']}").status_code == 409
    api.delete(f"/students/{student['id']}")
    assert api.delete(f"/courses/{course['id']}").status_code == 204
    assert api.get(f"/courses/{course['id']}").status_code == 404


# ------------------------------------------------------------ students ----
def test_register_student_unknown_category_rejected(api):
    course = api.course()
    res = api.post(
        "/students",
        json={
            "roll_no": "R1",
            "name": "A",
            "marks": 90,
            "category_code": "NOPE",
            "preferences": [{"course_id": course["id"], "priority": 1}],
        },
    )
    assert res.status_code == 422


def test_register_student_blank_name_rejected(api):
    res = api.post(
        "/students", json={"roll_no": "R1", "name": "   ", "marks": 50, "category_code": "SC"}
    )
    assert res.status_code == 422


def test_register_student_duplicate_roll_no_conflicts(api):
    course = api.course()
    api.student("R1", 90, "General", course["id"])
    res = api.post(
        "/students", json={"roll_no": "R1", "name": "B", "marks": 80, "category_code": "General"}
    )
    assert res.status_code == 409


def test_register_student_duplicate_preference_priority_rejected(api):
    course = api.course()
    res = api.post(
        "/students",
        json={
            "roll_no": "R2",
            "name": "C",
            "marks": 70,
            "category_code": "General",
            "preferences": [
                {"course_id": course["id"], "priority": 1},
                {"course_id": course["id"], "priority": 1},
            ],
        },
    )
    assert res.status_code == 400


def test_register_student_unknown_course_rejected(api):
    res = api.post(
        "/students",
        json={
            "roll_no": "R2",
            "name": "C",
            "marks": 70,
            "category_code": "General",
            "preferences": [{"course_id": 999, "priority": 1}],
        },
    )
    assert res.status_code == 400


def test_list_students_search_filter_and_pagination(api):
    course = api.course()
    api.student("A1", 90, "General", course["id"], name="Asha Rao")
    api.student("B1", 80, "OBC", course["id"], name="Bala Iyer")
    api.student("C1", 70, "OBC", course["id"], name="Chitra Rao")

    res = api.get("/students", params={"q": "rao"})
    assert res.headers["X-Total-Count"] == "2"
    assert [s["roll_no"] for s in res.json()] == ["A1", "C1"]  # merit order

    res = api.get("/students", params={"category": "OBC", "limit": 1, "offset": 1})
    assert res.headers["X-Total-Count"] == "2"
    assert [s["roll_no"] for s in res.json()] == ["C1"]


def test_update_student_changes_fields_and_preferences(api):
    a, b = api.course("A"), api.course("B")
    student = api.student("R1", 60, "General", [a["id"], b["id"]])
    res = api.put(
        f"/students/{student['id']}",
        json={
            "marks": 75.5,
            "category_code": "SC",
            "preferences": [
                {"course_id": b["id"], "priority": 1},
                {"course_id": a["id"], "priority": 2},
            ],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["marks"] == 75.5
    assert body["category"]["code"] == "SC"
    assert [p["course_id"] for p in sorted(body["preferences"], key=lambda p: p["priority"])] == [
        b["id"],
        a["id"],
    ]


def test_delete_student(api):
    course = api.course()
    student = api.student("R3", 60, "General", course["id"])
    assert api.delete(f"/students/{student['id']}").status_code == 204
    assert api.delete(f"/students/{student['id']}").status_code == 404


# ---------------------------------------------------------- csv import ----
def _import(api, text):
    return api.post("/students/import", content=text.encode(), headers={"Content-Type": "text/csv"})


def test_import_students_from_csv(api):
    api.course("Computer Science")
    api.course("Civil Engineering")
    text = (
        "roll_no,name,marks,category,application_date,preference_1,preference_2,preference_3\n"
        "X1,Asha Rao,88.5,General,2026-05-02,computer science,Civil Engineering,\n"
        "X2,Bala Iyer,71,obc,,Civil Engineering,,\n"
        "\n"
    )
    res = _import(api, text)
    assert res.status_code == 201, res.text
    assert res.json() == {"created": 2}
    students = {s["roll_no"]: s for s in api.get("/students").json()}
    assert students["X1"]["application_date"] == "2026-05-02"
    assert len(students["X1"]["preferences"]) == 2
    assert students["X2"]["category"]["code"] == "OBC"


def test_import_is_all_or_nothing_and_reports_every_bad_row(api):
    api.course("Computer Science")
    api.student("EXIST", 50, "General", [])
    text = (
        "roll_no,name,marks,category,preference_1\n"
        "Y1,Good Row,80,General,Computer Science\n"
        "Y2,Bad Marks,180,General,\n"
        "Y3,Bad Course,70,SC,Astrology\n"
        "EXIST,Dup Existing,60,ST,\n"
        "Y1,Dup In File,60,ST,\n"
        "Y6,Bad Category,60,XYZ,\n"
    )
    res = _import(api, text)
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert [e["row"] for e in detail["errors"]] == [3, 4, 5, 6, 7]
    assert api.get("/students").headers["X-Total-Count"] == "1"  # nothing imported


def test_import_requires_core_columns(api):
    res = _import(api, "roll_no,name\nA,B\n")
    assert res.status_code == 400
    assert "marks" in res.json()["detail"]


def test_import_template_is_valid_csv(api):
    api.course("Computer Science")
    res = api.get("/students/import/template")
    assert res.status_code == 200
    rows = list(csv.reader(io.StringIO(res.text)))
    assert rows[0][:4] == ["roll_no", "name", "marks", "category"]
    assert rows[1][5] == "Computer Science"


# ---------------------------------------------------------- allocation ----
def test_allocation_end_to_end_and_idempotent(api, admin_headers):
    # 1 open + 1 SC reserved seat.
    course = api.course(total_seats=2, quotas=[{"category_code": "SC", "reserved_seats": 1}])
    api.student("G1", 95, "General", course["id"])  # -> open seat
    api.student("S1", 60, "SC", course["id"])  # -> reserved seat
    api.student("G2", 50, "General", course["id"])  # -> no seat left

    result = api.post("/allocation/run").json()
    assert result["total_students"] == 3
    assert result["allocated"] == 2
    assert result["unallocated"] == 1
    assert result["run"]["triggered_by"] == "admin@test.edu"

    by_roll = {a["roll_no"]: a for a in result["allocations"]}
    assert by_roll["G1"]["seat_type"] == "open"
    assert by_roll["S1"]["seat_type"] == "reserved"
    assert "G2" not in by_roll

    # Idempotent: running again reproduces the same result, not a duplicate.
    assert api.post("/allocation/run").json()["allocated"] == 2
    assert len(api.get("/allocation").json()) == 2
    assert len(api.get("/allocation", params={"course_id": course["id"]}).json()) == 2

    unallocated = api.get("/allocation/unallocated").json()
    assert [u["roll_no"] for u in unallocated] == ["G2"]
    assert unallocated[0]["preferences"] == ["Computer Science"]

    runs = api.get("/allocation/runs").json()
    assert len(runs) == 2 and runs[0]["allocated"] == 2


def test_export_csv_lists_every_student(api):
    course = api.course(total_seats=1)
    api.student("E1", 90, "General", course["id"])
    api.student("E2", 80, "General", course["id"])
    api.post("/allocation/run")

    res = api.get("/allocation/export.csv")
    assert res.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(res.text)))
    assert {r["roll_no"]: r["status"] for r in rows} == {"E1": "allocated", "E2": "unallocated"}


def test_dashboard_stats_reflects_allocation(api):
    course = api.course(total_seats=1)
    api.student("D1", 90, "General", course["id"])
    api.student("D2", 80, "General", course["id"])
    api.post("/allocation/run")

    stats = api.get("/dashboard/stats").json()
    assert stats["total_students"] == 2
    assert stats["total_allocated"] == 1
    assert stats["total_unallocated"] == 1
    assert stats["allocation_rate"] == 0.5
    assert stats["seat_fill_rate"] == 1.0
    assert stats["highest_rejection_course"] == "Computer Science"
    assert stats["last_run"]["allocated"] == 1
    course_stat = stats["course_stats"][0]
    assert course_stat["applicants"] == 2
    assert course_stat["allocated"] == 1
    assert course_stat["rejection_rate"] == 0.5
    assert {p["preference_rank"]: p["allocated"] for p in stats["preference_stats"]} == {
        1: 1,
        2: 0,
        3: 0,
    }
    general = next(c for c in stats["category_stats"] if c["category_code"] == "General")
    assert general == {"category_code": "General", "students": 2, "allocated": 1}


def test_dashboard_on_empty_database(api):
    stats = api.get("/dashboard/stats").json()
    assert stats["total_students"] == 0
    assert stats["allocation_rate"] == 0.0
    assert stats["highest_rejection_course"] is None
    assert stats["last_run"] is None
