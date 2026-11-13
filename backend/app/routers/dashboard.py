"""Dashboard statistics: seats, allocations, category split, rejection rates."""

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..database import get_db

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Canonical "rejection rate" definition, shared with the AI assistant's
# fallback query (app/ai_assistant.py). For a course:
#   applicants     = distinct students who listed the course as ANY preference
#   allocated      = students allocated to this course
#   rejection_rate = (applicants - allocated) / applicants, rounded to 4 dp;
#                    0.0 when the course has no applicants.
# Note: this counts every applicant not placed in the course, including those
# who were placed in a higher preference elsewhere — so a roomy course that is
# mostly a 2nd/3rd choice can still show a high rate. Kept simple and identical
# on both the dashboard and the assistant so the two never disagree.
_REJECTION_RATE_DP = 4


def _ratio(num: int, den: int) -> float:
    return round(num / den, _REJECTION_RATE_DP) if den else 0.0


@router.get("/stats", response_model=schemas.DashboardStats)
def stats(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    total_students = db.query(models.Student).count()
    total_allocated = db.query(models.Allocation).count()

    alloc_by_course = dict(
        db.query(models.Allocation.course_id, func.count(models.Allocation.id))
        .group_by(models.Allocation.course_id)
        .all()
    )
    applicants_by_course = dict(
        db.query(
            models.Preference.course_id,
            func.count(func.distinct(models.Preference.student_id)),
        )
        .group_by(models.Preference.course_id)
        .all()
    )

    course_stats: list[schemas.CourseStat] = []
    for c in db.query(models.Course).order_by(models.Course.name).all():
        allocated = alloc_by_course.get(c.id, 0)
        applicants = applicants_by_course.get(c.id, 0)
        course_stats.append(
            schemas.CourseStat(
                course_id=c.id,
                course_name=c.name,
                total_seats=c.total_seats,
                allocated=allocated,
                available_seats=max(c.total_seats - allocated, 0),
                applicants=applicants,
                rejection_rate=_ratio(applicants - allocated, applicants),
            )
        )
    total_seats = sum(c.total_seats for c in course_stats)

    cat_rows = (
        db.query(
            models.Category.code,
            func.count(func.distinct(models.Student.id)),
            func.count(models.Allocation.id),
        )
        .outerjoin(models.Student, models.Student.category_id == models.Category.id)
        .outerjoin(models.Allocation, models.Allocation.student_id == models.Student.id)
        .group_by(models.Category.id, models.Category.code)
        .order_by(models.Category.id)
        .all()
    )
    category_stats = [
        schemas.CategoryStat(category_code=code, students=n_students, allocated=n_alloc)
        for code, n_students, n_alloc in cat_rows
    ]

    by_rank = dict(
        db.query(models.Allocation.preference_rank, func.count(models.Allocation.id))
        .group_by(models.Allocation.preference_rank)
        .all()
    )
    preference_stats = [
        schemas.PreferenceStat(preference_rank=r, allocated=by_rank.get(r, 0)) for r in (1, 2, 3)
    ]

    by_seat = dict(
        db.query(models.Allocation.seat_type, func.count(models.Allocation.id))
        .group_by(models.Allocation.seat_type)
        .all()
    )
    seat_type_stats = [
        schemas.SeatTypeStat(seat_type=t, allocated=by_seat.get(t, 0)) for t in ("open", "reserved")
    ]

    highest = max(course_stats, key=lambda s: (s.rejection_rate, s.applicants), default=None)
    last_run = (
        db.query(models.AllocationRun)
        .order_by(models.AllocationRun.run_at.desc(), models.AllocationRun.id.desc())
        .first()
    )
    return schemas.DashboardStats(
        total_students=total_students,
        total_courses=len(course_stats),
        total_seats=total_seats,
        total_allocated=total_allocated,
        total_unallocated=total_students - total_allocated,
        allocation_rate=_ratio(total_allocated, total_students),
        seat_fill_rate=_ratio(total_allocated, total_seats),
        course_stats=course_stats,
        category_stats=category_stats,
        preference_stats=preference_stats,
        seat_type_stats=seat_type_stats,
        highest_rejection_course=highest.course_name if highest and highest.applicants else None,
        last_run=schemas.AllocationRunOut.model_validate(last_run) if last_run else None,
    )
