"""Unit tests for the pure allocation engine (no DB required)."""
from datetime import date

from app.allocation import CourseInput, StudentInput, run_allocation


def _byid(results):
    return {r.student_id: r for r in results}


def test_higher_marks_get_priority():
    courses = [CourseInput(id=1, total_seats=1, reserved={})]
    students = [
        StudentInput(1, 90, date(2025, 1, 1), "General", [1]),
        StudentInput(2, 80, date(2025, 1, 1), "General", [1]),
    ]
    res = _byid(run_allocation(students, courses))
    assert 1 in res and res[1].course_id == 1
    assert 2 not in res  # only one seat, lower marks misses out


def test_tie_broken_by_application_date():
    courses = [CourseInput(id=1, total_seats=1, reserved={})]
    students = [
        StudentInput(1, 85, date(2025, 2, 1), "General", [1]),
        StudentInput(2, 85, date(2025, 1, 1), "General", [1]),  # earlier -> wins
    ]
    res = _byid(run_allocation(students, courses))
    assert 2 in res and 1 not in res


def test_falls_through_to_lower_preference():
    courses = [
        CourseInput(id=1, total_seats=1, reserved={}),
        CourseInput(id=2, total_seats=1, reserved={}),
    ]
    students = [
        StudentInput(1, 90, date(2025, 1, 1), "General", [1, 2]),
        StudentInput(2, 80, date(2025, 1, 1), "General", [1, 2]),  # course1 full -> course2
    ]
    res = _byid(run_allocation(students, courses))
    assert res[1].course_id == 1 and res[1].preference_rank == 1
    assert res[2].course_id == 2 and res[2].preference_rank == 2


def test_one_course_per_student():
    courses = [
        CourseInput(id=1, total_seats=5, reserved={}),
        CourseInput(id=2, total_seats=5, reserved={}),
    ]
    students = [StudentInput(1, 90, date(2025, 1, 1), "General", [1, 2])]
    res = run_allocation(students, courses)
    assert len(res) == 1  # never allocated to both


def test_reserved_seat_floor_for_category():
    # 1 open seat, 1 SC reserved seat. A high-merit General student takes the
    # open seat; a lower-merit SC student still gets the reserved seat.
    courses = [CourseInput(id=1, total_seats=2, reserved={"SC": 1})]
    students = [
        StudentInput(1, 95, date(2025, 1, 1), "General", [1]),
        StudentInput(2, 60, date(2025, 1, 1), "SC", [1]),
    ]
    res = _byid(run_allocation(students, courses))
    assert res[1].seat_type == "open"
    assert res[2].seat_type == "reserved"


def test_meritorious_reserved_takes_open_seat():
    # High-merit SC student takes the open seat (not the reserved one), leaving
    # the reserved seat free for the next SC applicant.
    courses = [CourseInput(id=1, total_seats=2, reserved={"SC": 1})]
    students = [
        StudentInput(1, 99, date(2025, 1, 1), "SC", [1]),
        StudentInput(2, 70, date(2025, 1, 1), "SC", [1]),
    ]
    res = _byid(run_allocation(students, courses))
    assert res[1].seat_type == "open"
    assert res[2].seat_type == "reserved"


def test_general_cannot_take_reserved_seat():
    # Only a reserved SC seat remains; a General student cannot be placed.
    courses = [CourseInput(id=1, total_seats=1, reserved={"SC": 1})]
    students = [StudentInput(1, 90, date(2025, 1, 1), "General", [1])]
    res = run_allocation(students, courses)
    assert res == []


def test_full_tie_broken_by_registration_order_regardless_of_input_order():
    # Same marks and same application date: the earlier-registered student
    # (lower id) wins, however the rows happen to be ordered. Regression test:
    # the order used to depend on the DB's (unspecified) row order.
    courses = [CourseInput(id=1, total_seats=1, reserved={})]
    a = StudentInput(7, 80, date(2025, 1, 1), "General", [1])
    b = StudentInput(3, 80, date(2025, 1, 1), "General", [1])
    for students in ([a, b], [b, a]):
        (winner,) = run_allocation(students, courses)
        assert winner.student_id == 3
