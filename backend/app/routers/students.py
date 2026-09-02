"""Student registration & listing."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import require_api_key
from ..database import get_db

router = APIRouter(prefix="/students", tags=["students"])


def _get_category(db: Session, code: str) -> models.Category:
    cat = db.query(models.Category).filter(models.Category.code == code).first()
    if not cat:
        raise HTTPException(400, f"Unknown category '{code}'")
    return cat


@router.post(
    "", response_model=schemas.StudentOut, status_code=201, dependencies=[Depends(require_api_key)]
)
def register_student(payload: schemas.StudentCreate, db: Session = Depends(get_db)):
    if db.query(models.Student).filter(models.Student.roll_no == payload.roll_no).first():
        raise HTTPException(409, f"Student '{payload.roll_no}' already exists")

    category = _get_category(db, payload.category_code)

    # Validate preferences: distinct priorities, distinct existing courses.
    priorities = [p.priority for p in payload.preferences]
    course_ids = [p.course_id for p in payload.preferences]
    if len(set(priorities)) != len(priorities):
        raise HTTPException(400, "Duplicate preference priorities")
    if len(set(course_ids)) != len(course_ids):
        raise HTTPException(400, "Duplicate preferred courses")
    for cid in course_ids:
        if not db.get(models.Course, cid):
            raise HTTPException(400, f"Course id {cid} does not exist")

    student = models.Student(
        roll_no=payload.roll_no,
        name=payload.name,
        marks=payload.marks,
        category_id=category.id,
        application_date=payload.application_date or date.today(),
        preferences=[
            models.Preference(course_id=p.course_id, priority=p.priority)
            for p in payload.preferences
        ],
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


@router.get("", response_model=list[schemas.StudentOut])
def list_students(db: Session = Depends(get_db)):
    return db.query(models.Student).order_by(models.Student.marks.desc()).all()


@router.delete("/{student_id}", status_code=204, dependencies=[Depends(require_api_key)])
def delete_student(student_id: int, db: Session = Depends(get_db)):
    student = db.get(models.Student, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    db.delete(student)
    db.commit()
