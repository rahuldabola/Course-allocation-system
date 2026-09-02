"""API-level tests: request validation, the allocation endpoint end-to-end,
dashboard aggregation, and API-key enforcement."""
from __future__ import annotations

from app.config import settings


def _make_course(client, name="Computer Science", total_seats=2, quotas=None):
    payload = {"name": name, "total_seats": total_seats, "quotas": quotas or []}
    res = client.post("/courses", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def _make_student(client, roll_no, marks, category_code, course_id, priority=1):
    payload = {
        "roll_no": roll_no,
        "name": f"Student {roll_no}",
        "marks": marks,
        "category_code": category_code,
        "preferences": [{"course_id": course_id, "priority": priority}],
    }
    res = client.post("/students", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_create_and_list_course(client):
    course = _make_course(client, quotas=[{"category_code": "SC", "reserved_seats": 1}])
    assert course["open_seats"] == 1
    assert client.get("/courses").json()[0]["name"] == "Computer Science"


def test_duplicate_course_name_conflicts(client):
    _make_course(client)
    res = client.post("/courses", json={"name": "Computer Science", "total_seats": 5, "quotas": []})
    assert res.status_code == 409


def test_reserved_seats_exceeding_total_seats_rejected(client):
    res = client.post(
        "/courses",
        json={
            "name": "X",
            "total_seats": 1,
            "quotas": [{"category_code": "SC", "reserved_seats": 2}],
        },
    )
    assert res.status_code == 400


def test_register_student_unknown_category_rejected(client):
    course = _make_course(client)
    res = client.post(
        "/students",
        json={
            "roll_no": "R1",
            "name": "A",
            "marks": 90,
            "category_code": "NOPE",
            "preferences": [{"course_id": course["id"], "priority": 1}],
        },
    )
    assert res.status_code == 400


def test_register_student_duplicate_roll_no_conflicts(client):
    course = _make_course(client)
    _make_student(client, "R1", 90, "General", course["id"])
    res = client.post(
        "/students",
        json={
            "roll_no": "R1",
            "name": "B",
            "marks": 80,
            "category_code": "General",
            "preferences": [],
        },
    )
    assert res.status_code == 409


def test_register_student_duplicate_preference_priority_rejected(client):
    course = _make_course(client)
    res = client.post(
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


def test_delete_student(client):
    course = _make_course(client)
    student = _make_student(client, "R3", 60, "General", course["id"])
    assert client.delete(f"/students/{student['id']}").status_code == 204
    assert client.delete(f"/students/{student['id']}").status_code == 404


def test_allocation_end_to_end_and_idempotent(client):
    # 1 open + 1 SC reserved seat.
    course = _make_course(
        client, total_seats=2, quotas=[{"category_code": "SC", "reserved_seats": 1}]
    )
    _make_student(client, "G1", 95, "General", course["id"])  # -> open seat
    _make_student(client, "S1", 60, "SC", course["id"])  # -> reserved seat
    _make_student(client, "G2", 50, "General", course["id"])  # -> no seat left

    result = client.post("/allocation/run").json()
    assert result["total_students"] == 3
    assert result["allocated"] == 2
    assert result["unallocated"] == 1

    by_roll = {a["roll_no"]: a for a in result["allocations"]}
    assert by_roll["G1"]["seat_type"] == "open"
    assert by_roll["S1"]["seat_type"] == "reserved"
    assert "G2" not in by_roll

    # Idempotent: running again reproduces the same result, not a duplicate.
    result2 = client.post("/allocation/run").json()
    assert result2["allocated"] == 2
    assert len(client.get("/allocation").json()) == 2


def test_dashboard_stats_reflects_allocation(client):
    course = _make_course(client, total_seats=1)
    _make_student(client, "D1", 90, "General", course["id"])
    _make_student(client, "D2", 80, "General", course["id"])
    client.post("/allocation/run")

    stats = client.get("/dashboard/stats").json()
    assert stats["total_students"] == 2
    assert stats["total_allocated"] == 1
    assert stats["total_unallocated"] == 1
    course_stat = stats["course_stats"][0]
    assert course_stat["applicants"] == 2
    assert course_stat["allocated"] == 1
    assert course_stat["rejection_rate"] == 0.5


def test_write_endpoints_require_api_key_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "secret-key")
    try:
        res = client.post("/courses", json={"name": "Locked", "total_seats": 1, "quotas": []})
        assert res.status_code == 401

        res = client.post(
            "/courses",
            json={"name": "Locked", "total_seats": 1, "quotas": []},
            headers={"X-API-Key": "wrong"},
        )
        assert res.status_code == 401

        res = client.post(
            "/courses",
            json={"name": "Locked", "total_seats": 1, "quotas": []},
            headers={"X-API-Key": "secret-key"},
        )
        assert res.status_code == 201
    finally:
        monkeypatch.setattr(settings, "api_key", "")


def test_read_endpoints_stay_open_when_api_key_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "secret-key")
    try:
        assert client.get("/courses").status_code == 200
    finally:
        monkeypatch.setattr(settings, "api_key", "")
