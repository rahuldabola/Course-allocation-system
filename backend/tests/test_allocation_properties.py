"""Property-based tests: invariants the allocation engine must hold for ANY input."""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from app.allocation import GENERAL, CourseInput, StudentInput, run_allocation

CATEGORIES = [GENERAL, "OBC", "SC", "ST"]


@st.composite
def scenarios(draw):
    n_courses = draw(st.integers(min_value=1, max_value=5))
    courses = []
    for cid in range(1, n_courses + 1):
        total = draw(st.integers(min_value=0, max_value=6))
        reserved: dict[str, int] = {}
        remaining = total
        for code in CATEGORIES[1:]:
            seats = draw(st.integers(min_value=0, max_value=remaining))
            if seats:
                reserved[code] = seats
            remaining -= seats
        courses.append(CourseInput(id=cid, total_seats=total, reserved=reserved))

    n_students = draw(st.integers(min_value=0, max_value=25))
    students = []
    for sid in range(1, n_students + 1):
        prefs = draw(
            st.lists(
                st.integers(min_value=1, max_value=n_courses), unique=True, min_size=0, max_size=3
            )
        )
        students.append(
            StudentInput(
                id=sid,
                marks=draw(st.integers(min_value=0, max_value=20)) * 5.0,  # force ties
                application_date=date(2026, 1, 1) + timedelta(days=draw(st.integers(0, 3))),
                category_code=draw(st.sampled_from(CATEGORIES)),
                preferences=prefs,
            )
        )
    return students, courses


def _open_seats(course: CourseInput) -> int:
    return max(course.total_seats - sum(course.reserved.values()), 0)


@settings(max_examples=300, deadline=None)
@given(scenarios())
def test_allocation_invariants(scenario):
    students, courses = scenario
    results = run_allocation(students, courses)
    by_student = {s.id: s for s in students}
    by_course = {c.id: c for c in courses}

    # 1. Each student gets at most one seat.
    assert len({r.student_id for r in results}) == len(results)

    # 2. Only courses the student asked for; rank matches the preference list.
    for r in results:
        prefs = by_student[r.student_id].preferences
        assert r.course_id in prefs
        assert prefs.index(r.course_id) + 1 == r.preference_rank

    # 3. Capacity: open and per-category reserved seats are never oversubscribed.
    open_used = Counter(r.course_id for r in results if r.seat_type == "open")
    reserved_used = Counter(
        (r.course_id, by_student[r.student_id].category_code)
        for r in results
        if r.seat_type == "reserved"
    )
    for course in courses:
        assert open_used[course.id] <= _open_seats(course)
    for (cid, code), used in reserved_used.items():
        assert used <= by_course[cid].reserved.get(code, 0)

    # 4. General-category students never occupy reserved seats.
    for r in results:
        if r.seat_type == "reserved":
            assert by_student[r.student_id].category_code != GENERAL

    # 5. No justified envy: nobody was skipped at a course in favour of a
    #    lower-merit student who took a seat the skipped student was eligible for.
    merit = {s.id: (-s.marks, s.application_date, s.id) for s in students}
    placed = {r.student_id: r for r in results}
    for s in students:
        got_rank = placed[s.id].preference_rank if s.id in placed else len(s.preferences) + 1
        for better_rank, cid in enumerate(s.preferences[: got_rank - 1], start=1):
            for r in results:
                if r.course_id != cid or merit[r.student_id] <= merit[s.id]:
                    continue
                other = by_student[r.student_id]
                eligible = r.seat_type == "open" or other.category_code == s.category_code
                assert not eligible, (
                    f"student {s.id} (pref {better_rank}) lost course {cid} to lower-merit "
                    f"student {other.id} ({r.seat_type} seat)"
                )


@settings(max_examples=100, deadline=None)
@given(scenarios())
def test_allocation_is_deterministic_and_order_independent(scenario):
    students, courses = scenario
    forward = run_allocation(students, courses)
    backward = run_allocation(list(reversed(students)), list(reversed(courses)))
    key = lambda r: r.student_id  # noqa: E731
    assert sorted(forward, key=key) == sorted(backward, key=key)
