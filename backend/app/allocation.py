"""Merit-order seat allocation engine with category reservation.

The core algorithm is written as a pure function (`run_allocation`) over plain
dataclasses so it can be unit-tested without a database. `allocate_and_persist`
is the thin DB-backed wrapper used by the API.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

GENERAL = "General"


@dataclass
class StudentInput:
    id: int
    marks: float
    application_date: date
    category_code: str
    preferences: list[int]  # ordered course ids, index 0 = priority 1


@dataclass
class CourseInput:
    id: int
    total_seats: int
    reserved: dict[str, int]  # category_code -> reserved seats


@dataclass
class AllocationResult:
    student_id: int
    course_id: int
    seat_type: str  # 'open' | 'reserved'
    preference_rank: int  # 1-based


@dataclass
class _CourseState:
    open_seats: int
    reserved: dict[str, int] = field(default_factory=dict)

    def can_admit(self, category_code: str) -> str | None:
        """Return the seat_type a student of this category can take, or None."""
        if self.open_seats > 0:
            # Merit-order processing means open seats go to the most meritorious
            # applicant regardless of category. Reserved students take open seats
            # when available, preserving reserved seats for lower-merit peers.
            return "open"
        if category_code != GENERAL and self.reserved.get(category_code, 0) > 0:
            return "reserved"
        return None

    def admit(self, seat_type: str, category_code: str) -> None:
        if seat_type == "open":
            self.open_seats -= 1
        else:
            self.reserved[category_code] -= 1


def _merit_key(s: StudentInput):
    # Higher marks first (negate), then earlier application date, then earlier
    # registration (id). The final key makes the order total, so results never
    # depend on the order rows happen to come back from the database.
    return (-s.marks, s.application_date, s.id)


def run_allocation(
    students: list[StudentInput], courses: list[CourseInput]
) -> list[AllocationResult]:
    """Allocate each student to at most one course following business rules:

    1. Higher marks -> higher priority; ties broken by earlier application date,
       then by earlier registration (student id).
    2. Reservation: open seats are merit-based; reserved seats guarantee a floor
       per category. Reserved-category students take an open seat when available,
       otherwise a reserved seat of their own category.
    3. Preferences evaluated in order; first available seat wins.
    4. A student matching none of their preferences stays unallocated.
    """
    state: dict[int, _CourseState] = {}
    for c in courses:
        reserved_total = sum(c.reserved.values())
        open_seats = max(c.total_seats - reserved_total, 0)
        state[c.id] = _CourseState(open_seats=open_seats, reserved=dict(c.reserved))

    results: list[AllocationResult] = []
    for student in sorted(students, key=_merit_key):
        for rank, course_id in enumerate(student.preferences, start=1):
            cs = state.get(course_id)
            if cs is None:
                continue
            seat_type = cs.can_admit(student.category_code)
            if seat_type is not None:
                cs.admit(seat_type, student.category_code)
                results.append(
                    AllocationResult(
                        student_id=student.id,
                        course_id=course_id,
                        seat_type=seat_type,
                        preference_rank=rank,
                    )
                )
                break
    return results


# --------------------------------------------------------------------------- #
# DB-backed wrapper
# --------------------------------------------------------------------------- #
def allocate_and_persist(db) -> list[AllocationResult]:
    """Load data from the DB, run allocation, and persist results idempotently."""
    from .models import Allocation, Course, CourseQuota, Preference, Student

    students_rows = db.query(Student).all()
    courses_rows = db.query(Course).all()
    quotas_rows = db.query(CourseQuota).all()
    prefs_rows = db.query(Preference).all()

    quota_by_course: dict[int, dict[str, int]] = {}
    for q in quotas_rows:
        quota_by_course.setdefault(q.course_id, {})[q.category.code] = q.reserved_seats

    prefs_by_student: dict[int, list[tuple[int, int]]] = {}
    for p in prefs_rows:
        prefs_by_student.setdefault(p.student_id, []).append((p.priority, p.course_id))

    students = [
        StudentInput(
            id=s.id,
            marks=s.marks,
            application_date=s.application_date,
            category_code=s.category.code,
            preferences=[cid for _, cid in sorted(prefs_by_student.get(s.id, []))],
        )
        for s in students_rows
    ]
    courses = [
        CourseInput(
            id=c.id,
            total_seats=c.total_seats,
            reserved=quota_by_course.get(c.id, {}),
        )
        for c in courses_rows
    ]

    results = run_allocation(students, courses)

    # Idempotent: clear previous allocations, then persist the fresh run.
    db.query(Allocation).delete()
    for r in results:
        db.add(
            Allocation(
                student_id=r.student_id,
                course_id=r.course_id,
                seat_type=r.seat_type,
                preference_rank=r.preference_rank,
            )
        )
    db.commit()
    return results
