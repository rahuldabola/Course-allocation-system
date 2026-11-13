"""Shared fixtures: a FastAPI TestClient over a throwaway database.

Tests run on SQLite by default (no services needed). Set TEST_DATABASE_URL to a
disposable Postgres database to run the same suite against Postgres (CI does).
The app's own DATABASE_URL is deliberately *not* reused, so running the tests
can never wipe a development database.
"""

from __future__ import annotations

import os
import tempfile

# Configure the app *before* app.config is imported (Settings() is built at import).
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", f"sqlite:///{tempfile.gettempdir()}/course_alloc_test_{os.getpid()}.db"
)
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "LLM_PROVIDER": "none",
        "DEMO_MODE": "false",
        "ADMIN_EMAIL": "",
        "ADMIN_PASSWORD": "",
        "JWT_SECRET": "test-secret-that-is-long-enough-for-hs256-0123456789",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.routers.assistant import assistant_limiter  # noqa: E402
from app.routers.auth import login_limiter  # noqa: E402
from app.security import create_access_token  # noqa: E402
from app.seed import ensure_categories, upsert_user  # noqa: E402

TEST_PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_db():
    """Start every test with an empty (but category-seeded) database."""
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    ensure_categories()
    login_limiter.reset()
    assistant_limiter.reset()
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_user():
    def _make(role: str = "admin", email: str | None = None, password: str = TEST_PASSWORD):
        with SessionLocal() as db:
            user = upsert_user(db, email or f"{role}@test.edu", role.title(), password, role)
            return user.id

    return _make


def _headers(user_id: int, role: str) -> dict[str, str]:
    token, _ = create_access_token(user_id, role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(make_user):
    return _headers(make_user("admin"), "admin")


@pytest.fixture
def viewer_headers(make_user):
    return _headers(make_user("viewer"), "viewer")
