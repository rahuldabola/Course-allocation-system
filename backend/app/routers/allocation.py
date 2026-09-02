"""Allocation processing & results."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..allocation import allocate_and_persist
from ..auth import require_api_key
from ..database import get_db

router = APIRouter(prefix="/allocation", tags=["allocation"])


def _serialize_allocations(db: Session) -> list[schemas.AllocationOut]:
    rows = (
        db.query(models.Allocation)
        .join(models.Student)
        .join(models.Course, models.Allocation.course_id == models.Course.id)
        .all()
    )
    out = []
    for a in rows:
        out.append(
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
        )
    out.sort(key=lambda x: (x.course_name, -x.marks))
    return out


@router.post(
    "/run", response_model=schemas.AllocationRunResult, dependencies=[Depends(require_api_key)]
)
def run(db: Session = Depends(get_db)):
    """(Re)compute allocation for all students. Idempotent."""
    allocate_and_persist(db)
    total = db.query(models.Student).count()
    allocations = _serialize_allocations(db)
    return schemas.AllocationRunResult(
        total_students=total,
        allocated=len(allocations),
        unallocated=total - len(allocations),
        allocations=allocations,
    )


@router.get("", response_model=list[schemas.AllocationOut])
def list_allocations(db: Session = Depends(get_db)):
    return _serialize_allocations(db)
