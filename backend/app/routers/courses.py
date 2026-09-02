"""Course management (create / list / update)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import require_api_key
from ..database import get_db

router = APIRouter(prefix="/courses", tags=["courses"])


def _category_map(db: Session) -> dict[str, models.Category]:
    return {c.code: c for c in db.query(models.Category).all()}


def _serialize(course: models.Course) -> schemas.CourseOut:
    reserved_total = sum(q.reserved_seats for q in course.quotas)
    return schemas.CourseOut(
        id=course.id,
        name=course.name,
        total_seats=course.total_seats,
        open_seats=max(course.total_seats - reserved_total, 0),
        quotas=[
            schemas.QuotaOut(category_code=q.category.code, reserved_seats=q.reserved_seats)
            for q in course.quotas
        ],
    )


def _apply_quotas(db: Session, course: models.Course, quotas: list[schemas.QuotaIn]):
    cats = _category_map(db)
    reserved_total = 0
    for q in quotas:
        if q.category_code not in cats:
            raise HTTPException(400, f"Unknown category '{q.category_code}'")
        reserved_total += q.reserved_seats
    if reserved_total > course.total_seats:
        raise HTTPException(400, "Reserved seats exceed total seats")
    course.quotas = [
        models.CourseQuota(category_id=cats[q.category_code].id, reserved_seats=q.reserved_seats)
        for q in quotas
    ]


@router.post(
    "", response_model=schemas.CourseOut, status_code=201, dependencies=[Depends(require_api_key)]
)
def create_course(payload: schemas.CourseCreate, db: Session = Depends(get_db)):
    if db.query(models.Course).filter(models.Course.name == payload.name).first():
        raise HTTPException(409, f"Course '{payload.name}' already exists")
    course = models.Course(name=payload.name, total_seats=payload.total_seats)
    _apply_quotas(db, course, payload.quotas)
    db.add(course)
    db.commit()
    db.refresh(course)
    return _serialize(course)


@router.get("", response_model=list[schemas.CourseOut])
def list_courses(db: Session = Depends(get_db)):
    return [_serialize(c) for c in db.query(models.Course).order_by(models.Course.name).all()]


@router.put(
    "/{course_id}", response_model=schemas.CourseOut, dependencies=[Depends(require_api_key)]
)
def update_course(course_id: int, payload: schemas.CourseUpdate, db: Session = Depends(get_db)):
    course = db.get(models.Course, course_id)
    if not course:
        raise HTTPException(404, "Course not found")
    if payload.name is not None:
        course.name = payload.name
    if payload.total_seats is not None:
        course.total_seats = payload.total_seats
    if payload.quotas is not None:
        _apply_quotas(db, course, payload.quotas)
    db.commit()
    db.refresh(course)
    return _serialize(course)
