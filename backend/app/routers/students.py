"""Student registration, listing, bulk CSV import, update and deletion."""

from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from ..auth import get_current_user, require_admin
from ..database import get_db

router = APIRouter(prefix="/students", tags=["students"])

MAX_IMPORT_BYTES = 1_000_000
MAX_IMPORT_ROWS = 5_000
IMPORT_COLUMNS = [
    "roll_no",
    "name",
    "marks",
    "category",
    "application_date",
    "preference_1",
    "preference_2",
    "preference_3",
]


def _eager(query):
    return query.options(
        selectinload(models.Student.category), selectinload(models.Student.preferences)
    )


def _get_category(db: Session, code: str) -> models.Category:
    cat = db.query(models.Category).filter(models.Category.code == code).first()
    if not cat:
        raise HTTPException(400, f"Unknown category '{code}'")
    return cat


def _validate_preferences(db: Session, prefs: list[schemas.PreferenceIn]) -> None:
    priorities = [p.priority for p in prefs]
    course_ids = [p.course_id for p in prefs]
    if len(set(priorities)) != len(priorities):
        raise HTTPException(400, "Duplicate preference priorities")
    if len(set(course_ids)) != len(course_ids):
        raise HTTPException(400, "Duplicate preferred courses")
    if course_ids:
        found = {
            cid for (cid,) in db.query(models.Course.id).filter(models.Course.id.in_(course_ids))
        }
        missing = sorted(set(course_ids) - found)
        if missing:
            raise HTTPException(400, f"Course id {missing[0]} does not exist")


def _get_student(db: Session, student_id: int) -> models.Student:
    student = _eager(db.query(models.Student)).filter(models.Student.id == student_id).first()
    if not student:
        raise HTTPException(404, "Student not found")
    return student


@router.post("", response_model=schemas.StudentOut, status_code=201)
def register_student(
    payload: schemas.StudentCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    if db.query(models.Student).filter(models.Student.roll_no == payload.roll_no).first():
        raise HTTPException(409, f"Student '{payload.roll_no}' already exists")
    category = _get_category(db, payload.category_code)
    _validate_preferences(db, payload.preferences)

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
    return _get_student(db, student.id)


@router.get("", response_model=list[schemas.StudentOut])
def list_students(
    response: Response,
    q: str | None = Query(default=None, max_length=100, description="Search name or roll no"),
    category: schemas.CategoryCode | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    """List students by merit (marks desc, earlier application first).

    The total number of matches (before paging) is returned in `X-Total-Count`.
    """
    query = db.query(models.Student)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(models.Student.name.ilike(like), models.Student.roll_no.ilike(like))
        )
    if category:
        query = query.join(models.Category).filter(models.Category.code == category)
    response.headers["X-Total-Count"] = str(query.count())
    return (
        _eager(query)
        .order_by(models.Student.marks.desc(), models.Student.application_date, models.Student.id)
        .offset(offset)
        .limit(limit)
        .all()
    )


async def _csv_body(request: Request) -> str:
    body = await request.body()
    if len(body) > MAX_IMPORT_BYTES:
        raise HTTPException(413, f"CSV larger than {MAX_IMPORT_BYTES // 1000} KB")
    try:
        return body.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(400, "CSV must be UTF-8 encoded") from None


def _format_validation_error(e: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in err['loc']) or 'row'}: {err['msg']}" for err in e.errors()
    )


@router.post(
    "/import",
    response_model=schemas.ImportResult,
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"text/csv": {"schema": {"type": "string"}}},
        }
    },
)
def import_students(
    text: str = Depends(_csv_body),
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    """Bulk-register students from CSV (all-or-nothing).

    Columns: `roll_no,name,marks,category,application_date,preference_1,preference_2,
    preference_3`. `application_date` (YYYY-MM-DD) and the preferences are optional;
    preferences are course names. If any row is invalid nothing is imported and the
    response lists every problem by line number.
    """
    reader = csv.DictReader(io.StringIO(text))
    header = [h.strip().lower() for h in (reader.fieldnames or [])]
    missing = [c for c in ("roll_no", "name", "marks", "category") if c not in header]
    if missing:
        raise HTTPException(400, f"CSV is missing required column(s): {', '.join(missing)}")
    reader.fieldnames = header

    courses_by_name = {c.name.lower(): c for c in db.query(models.Course).all()}
    categories = {c.code.lower(): c for c in db.query(models.Category).all()}
    existing_rolls = {r for (r,) in db.query(models.Student.roll_no)}
    seen_rolls: set[str] = set()
    errors: list[schemas.ImportRowError] = []
    to_create: list[models.Student] = []

    for line_no, row in enumerate(reader, start=2):
        if line_no - 1 > MAX_IMPORT_ROWS:
            raise HTTPException(400, f"CSV has more than {MAX_IMPORT_ROWS} rows")
        row = {k: (v or "").strip() for k, v in row.items() if k}
        if not any(row.values()):
            continue  # blank line
        try:
            pref_names = [row.get(f"preference_{i}", "") for i in (1, 2, 3)]
            pref_names = [n for n in pref_names if n]
            unknown = [n for n in pref_names if n.lower() not in courses_by_name]
            if unknown:
                raise ValueError(f"unknown course '{unknown[0]}'")
            category = categories.get(row.get("category", "").lower())
            if category is None:
                raise ValueError(f"unknown category '{row.get('category', '')}'")
            payload = schemas.StudentCreate(
                roll_no=row.get("roll_no", ""),
                name=row.get("name", ""),
                marks=row.get("marks", ""),
                category_code=category.code,
                application_date=row.get("application_date") or None,
                preferences=[
                    schemas.PreferenceIn(course_id=courses_by_name[n.lower()].id, priority=i)
                    for i, n in enumerate(pref_names, start=1)
                ],
            )
            if len({p.course_id for p in payload.preferences}) != len(payload.preferences):
                raise ValueError("the same course is listed more than once")
            if payload.roll_no in existing_rolls:
                raise ValueError(f"roll_no '{payload.roll_no}' already exists")
            if payload.roll_no in seen_rolls:
                raise ValueError(f"roll_no '{payload.roll_no}' appears twice in this file")
        except ValidationError as e:
            errors.append(schemas.ImportRowError(row=line_no, message=_format_validation_error(e)))
            continue
        except ValueError as e:
            errors.append(schemas.ImportRowError(row=line_no, message=str(e)))
            continue
        seen_rolls.add(payload.roll_no)
        to_create.append(
            models.Student(
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
        )

    if errors:
        raise HTTPException(
            422,
            detail={
                "message": f"{len(errors)} row(s) have errors; nothing was imported.",
                "errors": [e.model_dump() for e in errors[:100]],
            },
        )
    if not to_create:
        raise HTTPException(400, "CSV contains no student rows")
    db.add_all(to_create)
    db.commit()
    return schemas.ImportResult(created=len(to_create))


@router.get("/import/template", response_class=Response)
def import_template(db: Session = Depends(get_db), _: models.User = Depends(get_current_user)):
    """A CSV template with the expected header and one example row."""
    names = [c for (c,) in db.query(models.Course.name).order_by(models.Course.name).limit(3)]
    names += [""] * (3 - len(names))
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(IMPORT_COLUMNS)
    writer.writerow(["2026X001", "Asha Rao", "88.5", "General", "2026-05-12", *names])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="students_template.csv"'},
    )


@router.get("/{student_id}", response_model=schemas.StudentOut)
def get_student(
    student_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(get_current_user),
):
    return _get_student(db, student_id)


@router.put("/{student_id}", response_model=schemas.StudentOut)
def update_student(
    student_id: int,
    payload: schemas.StudentUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    student = _get_student(db, student_id)
    if payload.name is not None:
        student.name = payload.name
    if payload.marks is not None:
        student.marks = payload.marks
    if payload.category_code is not None:
        student.category_id = _get_category(db, payload.category_code).id
    if payload.application_date is not None:
        student.application_date = payload.application_date
    if payload.preferences is not None:
        _validate_preferences(db, payload.preferences)
        # Flush the removals first so the (student_id, priority) unique
        # constraint doesn't trip when a priority is reused.
        student.preferences = []
        db.flush()
        student.preferences = [
            models.Preference(course_id=p.course_id, priority=p.priority)
            for p in payload.preferences
        ]
    db.commit()
    db.expire_all()
    return _get_student(db, student_id)


@router.delete("/{student_id}", status_code=204)
def delete_student(
    student_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_admin),
):
    student = db.get(models.Student, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    db.delete(student)
    db.commit()
