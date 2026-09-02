"""Dashboard statistics: seats, allocations, category split, rejection rates."""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
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


@router.get("/stats", response_model=schemas.DashboardStats)
def stats(db: Session = Depends(get_db)):
    total_students = db.query(models.Student).count()
    total_allocated = db.query(models.Allocation).count()

    # allocated count per course
    alloc_by_course = dict(
        db.query(models.Allocation.course_id, func.count(models.Allocation.id))
        .group_by(models.Allocation.course_id)
        .all()
    )
    # applicants per course (listed it as any preference)
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
        # Rejection rate: applicants to the course who were NOT allocated to it.
        rejection_rate = (
            round((applicants - allocated) / applicants, _REJECTION_RATE_DP)
            if applicants
            else 0.0
        )
        course_stats.append(
            schemas.CourseStat(
                course_id=c.id,
                course_name=c.name,
                total_seats=c.total_seats,
                allocated=allocated,
                available_seats=max(c.total_seats - allocated, 0),
                applicants=applicants,
                rejection_rate=rejection_rate,
            )
        )

    # category-wise allocation
    cat_rows = (
        db.query(models.Category.code, func.count(models.Allocation.id))
        .outerjoin(models.Student, models.Student.category_id == models.Category.id)
        .outerjoin(models.Allocation, models.Allocation.student_id == models.Student.id)
        .group_by(models.Category.code)
        .all()
    )
    category_stats = [schemas.CategoryStat(category_code=code, allocated=n) for code, n in cat_rows]

    highest = max(
        course_stats, key=lambda s: (s.rejection_rate, s.applicants), default=None
    )
    return schemas.DashboardStats(
        total_students=total_students,
        total_allocated=total_allocated,
        total_unallocated=total_students - total_allocated,
        course_stats=course_stats,
        category_stats=category_stats,
        highest_rejection_course=highest.course_name if highest and highest.applicants else None,
    )
