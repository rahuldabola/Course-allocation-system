"""Seed helpers: base categories + sample dataset for demos.

Run `alembic upgrade head` first to create the schema, then
`python -m app.seed` to populate sample courses and students.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from . import models
from .database import SessionLocal

CATEGORIES = [
    ("General", "General / Open"),
    ("OBC", "Other Backward Classes"),
    ("SC", "Scheduled Caste"),
    ("ST", "Scheduled Tribe"),
]


def ensure_categories():
    db = SessionLocal()
    try:
        existing = {c.code for c in db.query(models.Category).all()}
        for code, name in CATEGORIES:
            if code not in existing:
                db.add(models.Category(code=code, name=name))
        db.commit()
    finally:
        db.close()


SAMPLE_COURSES = [
    # name, total_seats, {category: reserved}
    ("Computer Science", 10, {"OBC": 2, "SC": 1, "ST": 1}),
    ("Electronics", 8, {"OBC": 2, "SC": 1, "ST": 1}),
    ("Mechanical", 12, {"OBC": 3, "SC": 1, "ST": 1}),
    ("Civil", 10, {"OBC": 2, "SC": 1, "ST": 1}),
    ("Biotechnology", 6, {"OBC": 1, "SC": 1, "ST": 0}),
]

FIRST_NAMES = ["Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan",
               "Krishna", "Ishaan", "Ananya", "Diya", "Aadhya", "Saanvi", "Pari", "Myra",
               "Anika", "Navya", "Kiara", "Riya"]
LAST_NAMES = ["Sharma", "Verma", "Gupta", "Singh", "Kumar", "Reddy", "Nair", "Iyer",
              "Patel", "Das"]


def seed_sample(n_students: int = 50, seed: int = 42):
    random.seed(seed)
    db = SessionLocal()
    try:
        ensure_categories()
        cats = {c.code: c for c in db.query(models.Category).all()}

        # Wipe prior demo data (order matters for FKs).
        db.query(models.Allocation).delete()
        db.query(models.Preference).delete()
        db.query(models.Student).delete()
        db.query(models.CourseQuota).delete()
        db.query(models.Course).delete()
        db.commit()

        courses = []
        for name, total, reserved in SAMPLE_COURSES:
            course = models.Course(name=name, total_seats=total)
            course.quotas = [
                models.CourseQuota(category_id=cats[code].id, reserved_seats=seats)
                for code, seats in reserved.items()
            ]
            db.add(course)
            courses.append(course)
        db.commit()

        category_pool = ["General"] * 5 + ["OBC"] * 3 + ["SC"] * 2 + ["ST"] * 1
        base_date = date(2025, 5, 1)
        for i in range(1, n_students + 1):
            cat = random.choice(category_pool)
            name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            prefs = random.sample(courses, k=3)
            student = models.Student(
                roll_no=f"2025{i:04d}",
                name=name,
                marks=round(random.uniform(45, 99), 1),
                category_id=cats[cat].id,
                application_date=base_date + timedelta(days=random.randint(0, 30)),
                preferences=[
                    models.Preference(course_id=c.id, priority=rank)
                    for rank, c in enumerate(prefs, start=1)
                ],
            )
            db.add(student)
        db.commit()
        print(f"Seeded {len(courses)} courses and {n_students} students.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_sample()
