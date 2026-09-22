"""Allocation processing, results, history and export."""

import csv
import io

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..allocation import allocate_and_persist
from ..auth import get_current_user, require_admin
from ..database import get_db

router = APIRouter(prefix="/allocation", tags=["allocation"])


def _serialize_allocations(
    db: Session, course_id: int | None = None
) -> list[schemas.AllocationOut]:
    query = db.query(models.Allocation).options(
        selectinload(models.Allocation.student).selectinload(models.Student.category),
        selectinload(models.Allocation.course),
    )
    if course_id is not None:
        query = query.filter(models.Allocation.course_id == course_id)
    out = [
        schemas.AllocationOut(
            student_id=a.student_id,
            roll_no=a.student.roll_no,
            student_name=a.student.name,
            marks=a.student.marks,
            category_code=a.student.category.code,
            course_id=a.course_id,
            course_name=a.course.name,
            seat_type=a.seat_type,
            preference_rank=a.preference_rank,
        )
        for a in query.all()
    ]
    out.sort(key=lambda x: (x.course_name, -x.marks, x.roll_no))
    return out


def _unallocated(db: Session) -> list[schemas.UnallocatedStudentOut]:
    course_names = dict(db.query(models.Course.id, models.Course.name).all())
    students = (
        db.query(models.Student)
        .outerjoin(models.Allocation)
        .filter(models.Allocation.id.is_(None))
        .options(selectinload(models.Student.category), selectinload(models.Student.preferences))
        .order_by(models.Student.marks.desc(), models.Student.application_date)
        .all()
    )
    return [
        schemas.UnallocatedStudentOut(
            student_id=s.id,
            roll_no=s.roll_no,
            student_name=s.name,
            marks=s.marks,
            category_code=s.category.code,
            preferences=[course_names.get(p.course_id, f"#{p.course_id}") for p in s.preferences],
        )
        for s in students
    ]


@router.post("/run", response_model=schemas.AllocationRunResult)
def run(db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    """(Re)compute allocation for all students. Idempotent."""
    results, run_row = allocate_and_persist(db, triggered_by=admin.email)
    allocations = _serialize_allocations(db)
    return schemas.AllocationRunResult(
        total_students=run_row.total_students,
        allocated=len(results),
        unallocated=run_row.total_students - len(results),
        run=schemas.AllocationRunOut.model_validate(run_row),
        allocations=allocations,
    )


@router.get("", response_model=list[schemas.AllocationOut])
def list_allocations(
    course_id: int | None = None,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    return _serialize_allocations(db, course_id)


@router.get("/unallocated", response_model=list[schemas.UnallocatedStudentOut])
def list_unallocated(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    """Students without a seat (as of the latest run), by merit."""
    return _unallocated(db)


@router.get("/runs", response_model=list[schemas.AllocationRunOut])
def list_runs(
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    """Most recent allocation runs (audit trail)."""
    return (
        db.query(models.AllocationRun)
        .order_by(models.AllocationRun.run_at.desc(), models.AllocationRun.id.desc())
        .limit(limit)
        .all()
    )


@router.get("/export.csv", response_class=Response)
def export_csv(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    """Every student with their allocation outcome, as CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["roll_no", "name", "marks", "category", "status", "course", "seat_type", "preference_rank"]
    )
    for a in _serialize_allocations(db):
        writer.writerow(
            [
                a.roll_no,
                a.student_name,
                a.marks,
                a.category_code,
                "allocated",
                a.course_name,
                a.seat_type,
                a.preference_rank,
            ]
        )
    for s in _unallocated(db):
        writer.writerow(
            [s.roll_no, s.student_name, s.marks, s.category_code, "unallocated", "", "", ""]
        )
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="allocation_results.csv"'},
    )
