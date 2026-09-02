"""Shared fixtures: a SQLite-backed FastAPI TestClient (no Postgres needed)."""
from __future__ import annotations

import os
import tempfile

# Point the app at a throwaway SQLite file *before* app.config is imported,
# since Settings() is instantiated at import time.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mktemp(suffix='.db')}")
os.environ.setdefault("API_KEY", "")

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app
from app.seed import ensure_categories


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_db():
    """Start every test with an empty (but category-seeded) database."""
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    ensure_categories()
    yield


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
