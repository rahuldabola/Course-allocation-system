"""Course management (create / list / get / update / delete)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..auth import get_current_user, require_admin
from ..database import get_db

router = APIRouter(prefix="/courses", tags=["courses"])


def _applicant_counts(db: Session) -> dict[int, int]:
    return dict(
        db.query(
            models.Preference.course_id, func.count(func.distinct(models.Preference.student_id))
        )
        .group_by(models.Preference.course_id)
        .all()
    )


def _serialize(course: models.Course, applicants: int) -> schemas.CourseOut:
    reserved_total = sum(q.reserved_seats for q in course.quotas)
    return schemas.CourseOut(
        id=course.id,
        name=course.name,
        total_seats=course.total_seats,
        open_seats=max(course.total_seats - reserved_total, 0),
        applicants=applicants,
        quotas=[
            schemas.QuotaOut(category_code=q.category.code, reserved_seats=q.reserved_seats)
            for q in sorted(course.quotas, key=lambda q: q.category_id)
        ],
    )


def _load(db: Session, course_id: int) -> models.Course:
    course = (
        db.query(models.Course)
        .options(selectinload(models.Course.quotas).selectinload(models.CourseQuota.category))
        .filter(models.Course.id == course_id)
        .first()
    )
    if not course:
        raise HTTPException(404, "Course not found")
    return course


def _out(db: Session, course_id: int) -> schemas.CourseOut:
    return _serialize(_load(db, course_id), _applicant_counts(db).get(course_id, 0))


def _check_name_available(db: Session, name: str, exclude_id: int | None = None) -> None:
    query = db.query(models.Course).filter(func.lower(models.Course.name) == name.lower())
    if exclude_id is not None:
        query = query.filter(models.Course.id != exclude_id)
    if query.first():
        raise HTTPException(409, f"Course '{name}' already exists")


def _set_quotas(db: Session, course: models.Course, quotas: list[schemas.QuotaIn]) -> None:
    codes = [q.category_code for q in quotas]
    if len(set(codes)) != len(codes):
        raise HTTPException(400, "Each category may appear only once in quotas")
    cats = {c.code: c for c in db.query(models.Category).all()}
    course.quotas = [
        models.CourseQuota(category_id=cats[q.category_code].id, reserved_seats=q.reserved_seats)
        for q in quotas
        if q.reserved_seats > 0
    ]


def _check_capacity(total_seats: int, reserved: int) -> None:
    if reserved > total_seats:
        raise HTTPException(400, f"Reserved seats ({reserved}) exceed total seats ({total_seats})")


@router.post("", response_model=schemas.CourseOut, status_code=201)
def create_course(
    payload: schemas.CourseCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    _check_name_available(db, payload.name)
    _check_capacity(payload.total_seats, sum(q.reserved_seats for q in payload.quotas))
    course = models.Course(name=payload.name, total_seats=payload.total_seats)
    _set_quotas(db, course, payload.quotas)
    db.add(course)
    db.commit()
    return _out(db, course.id)


@router.get("", response_model=list[schemas.CourseOut])
def list_courses(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    applicants = _applicant_counts(db)
    courses = (
        db.query(models.Course)
        .options(selectinload(models.Course.quotas).selectinload(models.CourseQuota.category))
        .order_by(models.Course.name)
        .all()
    )
    return [_serialize(c, applicants.get(c.id, 0)) for c in courses]


@router.get("/{course_id}", response_model=schemas.CourseOut)
def get_course(
    course_id: int, db: Session = Depends(get_db), _: models.User = Depends(get_current_user)
):
    return _out(db, course_id)


@router.put("/{course_id}", response_model=schemas.CourseOut)
def update_course(
    course_id: int,
    payload: schemas.CourseUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    course = _load(db, course_id)
    if payload.name is not None and payload.name != course.name:
        _check_name_available(db, payload.name, exclude_id=course_id)
        course.name = payload.name
    total_seats = payload.total_seats if payload.total_seats is not None else course.total_seats
    reserved = (
        sum(q.reserved_seats for q in payload.quotas)
        if payload.quotas is not None
        else sum(q.reserved_seats for q in course.quotas)
    )
    # Validate the resulting state, whichever of seats/quotas changed.
    _check_capacity(total_seats, reserved)
    course.total_seats = total_seats
    if payload.quotas is not None:
        course.quotas = []
        db.flush()  # drop old quota rows before re-inserting (unique course/category)
        _set_quotas(db, course, payload.quotas)
    db.commit()
    db.expire_all()
    return _out(db, course_id)


@router.delete("/{course_id}", status_code=204)
def delete_course(
    course_id: int, db: Session = Depends(get_db), _: models.User = Depends(require_admin)
):
    """Delete a course. Refused while any student lists it as a preference."""
    course = db.get(models.Course, course_id)
    if not course:
        raise HTTPException(404, "Course not found")
    referenced = (
        db.query(func.count(models.Preference.id))
        .filter(models.Preference.course_id == course_id)
        .scalar()
    )
    if referenced:
        raise HTTPException(
            409,
            f"{referenced} student(s) list '{course.name}' as a preference; "
            "update or remove those students first.",
        )
    db.query(models.Allocation).filter(models.Allocation.course_id == course_id).delete()
    db.delete(course)
    db.commit()
