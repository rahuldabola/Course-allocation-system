"""Seed helpers: base categories, bootstrap users, and a sample dataset.

Run `alembic upgrade head` first to create the schema, then
`python -m app.seed` to (re)populate sample courses and students.
"""

from __future__ import annotations

import logging
import random
from datetime import date, timedelta

from sqlalchemy.orm import Session

from . import models
from .config import settings
from .database import SessionLocal
from .security import hash_password, verify_password

log = logging.getLogger(__name__)

CATEGORIES = [
    ("General", "General / Open"),
    ("OBC", "Other Backward Classes"),
    ("SC", "Scheduled Caste"),
    ("ST", "Scheduled Tribe"),
]

# Public demo credentials — only created when DEMO_MODE is on, and listed by
# GET /meta so the login page can offer one-click sign-in.
DEMO_PASSWORD = "demo1234"
DEMO_ACCOUNTS = [
    ("admin@demo.edu", "Demo Admin", "admin"),
    ("viewer@demo.edu", "Demo Viewer", "viewer"),
]


def ensure_categories(db: Session | None = None) -> None:
    own = db is None
    db = db or SessionLocal()
    try:
        existing = {c.code for c in db.query(models.Category).all()}
        for code, name in CATEGORIES:
            if code not in existing:
                db.add(models.Category(code=code, name=name))
        db.commit()
    finally:
        if own:
            db.close()


def upsert_user(db: Session, email: str, full_name: str, password: str, role: str) -> models.User:
    """Create the user, or make an existing one match the given password/role."""
    email = email.strip().lower()
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        user = models.User(
            email=email, full_name=full_name, password_hash=hash_password(password), role=role
        )
        db.add(user)
    else:
        if not verify_password(password, user.password_hash):
            user.password_hash = hash_password(password)
        user.role = role
        user.is_active = True
    db.commit()
    return user


def ensure_users(db: Session) -> None:
    if settings.admin_email and settings.admin_password:
        upsert_user(db, settings.admin_email, "Administrator", settings.admin_password, "admin")
    if settings.demo_mode:
        for email, name, role in DEMO_ACCOUNTS:
            upsert_user(db, email, name, DEMO_PASSWORD, role)


# --------------------------------------------------------------------------- #
# Sample dataset
# --------------------------------------------------------------------------- #
SAMPLE_COURSES = [
    # name, total_seats, {category: reserved}, relative popularity
    ("Computer Science", 12, {"OBC": 3, "SC": 2, "ST": 1}, 10),
    ("Data Science & AI", 10, {"OBC": 3, "SC": 1, "ST": 1}, 9),
    ("Electronics & Communication", 10, {"OBC": 3, "SC": 1, "ST": 1}, 6),
    ("Mechanical Engineering", 12, {"OBC": 3, "SC": 2, "ST": 1}, 4),
    ("Civil Engineering", 10, {"OBC": 3, "SC": 1, "ST": 1}, 3),
    ("Biotechnology", 8, {"OBC": 2, "SC": 1, "ST": 1}, 3),
]

FIRST_NAMES = [
    "Aarav",
    "Vivaan",
    "Aditya",
    "Vihaan",
    "Arjun",
    "Sai",
    "Reyansh",
    "Ayaan",
    "Krishna",
    "Ishaan",
    "Ananya",
    "Diya",
    "Aadhya",
    "Saanvi",
    "Pari",
    "Myra",
    "Anika",
    "Navya",
    "Kiara",
    "Riya",
    "Kabir",
    "Rohan",
    "Meera",
    "Tara",
    "Nikhil",
    "Pooja",
    "Harsh",
    "Sneha",
    "Dev",
    "Isha",
    "Yash",
    "Aditi",
    "Karan",
    "Neha",
    "Rahul",
    "Priya",
    "Om",
    "Kavya",
    "Arnav",
    "Zara",
]
LAST_NAMES = [
    "Sharma",
    "Verma",
    "Gupta",
    "Singh",
    "Kumar",
    "Reddy",
    "Nair",
    "Iyer",
    "Patel",
    "Das",
    "Mehta",
    "Joshi",
    "Rao",
    "Bose",
    "Chopra",
    "Malhotra",
    "Pillai",
    "Kulkarni",
    "Mishra",
    "Banerjee",
]


def _weighted_sample(rng: random.Random, items: list, weights: list[float], k: int) -> list:
    """k distinct items, drawn without replacement proportionally to weight."""
    pool, w, chosen = list(items), list(weights), []
    for _ in range(k):
        pick = rng.choices(range(len(pool)), weights=w, k=1)[0]
        chosen.append(pool.pop(pick))
        w.pop(pick)
    return chosen


def seed_sample(db: Session, n_students: int = 120, seed: int = 42) -> None:
    """Replace all courses/students/allocations with a deterministic sample dataset."""
    rng = random.Random(seed)
    ensure_categories(db)
    cats = {c.code: c for c in db.query(models.Category).all()}

    # Wipe prior data (order matters for FKs).
    for model in (
        models.Allocation,
        models.AllocationRun,
        models.Preference,
        models.Student,
        models.CourseQuota,
        models.Course,
    ):
        db.query(model).delete()
    db.commit()

    courses, popularity = [], []
    for name, total, reserved, weight in SAMPLE_COURSES:
        course = models.Course(name=name, total_seats=total)
        course.quotas = [
            models.CourseQuota(category_id=cats[code].id, reserved_seats=seats)
            for code, seats in reserved.items()
        ]
        db.add(course)
        courses.append(course)
        popularity.append(weight)
    db.commit()

    category_pool = ["General"] * 50 + ["OBC"] * 27 + ["SC"] * 15 + ["ST"] * 8
    base_date = date(2026, 5, 1)
    used_names: set[str] = set()
    for i in range(1, n_students + 1):
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        while name in used_names:
            name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        used_names.add(name)
        prefs = _weighted_sample(rng, courses, popularity, k=3)
        db.add(
            models.Student(
                roll_no=f"2026{i:04d}",
                name=name,
                marks=round(min(99.5, max(35.0, rng.gauss(72, 12))), 1),
                category_id=cats[rng.choice(category_pool)].id,
                application_date=base_date + timedelta(days=rng.randint(0, 30)),
                preferences=[
                    models.Preference(course_id=c.id, priority=rank)
                    for rank, c in enumerate(prefs, start=1)
                ],
            )
        )
    db.commit()
    log.info("Seeded %d courses and %d students", len(courses), n_students)


def reset_demo(db: Session, triggered_by: str | None = None) -> None:
    """Reload the sample dataset and run allocation, so the dashboard is populated."""
    from .allocation import allocate_and_persist

    seed_sample(db)
    allocate_and_persist(db, triggered_by=triggered_by)


def bootstrap(db: Session) -> None:
    """Startup tasks: categories, bootstrap users, and demo data for an empty DB."""
    ensure_categories(db)
    ensure_users(db)
    if settings.demo_mode and db.query(models.Course).count() == 0:
        log.info("Demo mode with an empty database: loading sample data")
        reset_demo(db, triggered_by="system")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    session = SessionLocal()
    try:
        seed_sample(session)
        print("Seeded sample courses and students. Run allocation from the UI or API.")
    finally:
        session.close()
