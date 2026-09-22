"""Demo-mode bootstrap, sample data, settings validation and LLM selection."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app import llm as llm_module
from app.config import _DEV_JWT_SECRET, Settings, settings
from app.database import SessionLocal
from app.models import AllocationRun, Course, Student, User
from app.seed import DEMO_PASSWORD, bootstrap, seed_sample


@pytest.fixture
def demo_mode(monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)


def test_bootstrap_in_demo_mode_seeds_accounts_data_and_allocation(demo_mode):
    with SessionLocal() as db:
        bootstrap(db)
        assert {u.email: u.role for u in db.query(User)} == {
            "admin@demo.edu": "admin",
            "viewer@demo.edu": "viewer",
        }
        assert db.query(Course).count() == 6
        assert db.query(Student).count() == 120
        run = db.query(AllocationRun).one()
        assert run.triggered_by == "system"
        assert 0 < run.allocated <= 62  # total seats in the sample dataset

        # Idempotent: a restart doesn't reseed or duplicate anything.
        bootstrap(db)
        assert db.query(AllocationRun).count() == 1
        assert db.query(User).count() == 2


def test_sample_dataset_is_deterministic():
    with SessionLocal() as db:
        seed_sample(db)
        first = [(s.roll_no, s.name, s.marks) for s in db.query(Student).order_by(Student.id)]
        seed_sample(db)
        second = [(s.roll_no, s.name, s.marks) for s in db.query(Student).order_by(Student.id)]
    assert first == second
    assert len({name for _, name, _ in first}) == len(first)  # names are unique


def test_demo_accounts_listed_and_usable(client, demo_mode):
    with SessionLocal() as db:
        bootstrap(db)
    meta = client.get("/meta").json()
    assert meta["demo_mode"] is True
    assert {a["email"] for a in meta["demo_accounts"]} == {"admin@demo.edu", "viewer@demo.edu"}

    res = client.post("/auth/login", json={"email": "admin@demo.edu", "password": DEMO_PASSWORD})
    assert res.status_code == 200
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}

    # Wreck the data, then reset it.
    for student in client.get("/students", params={"limit": 5}, headers=headers).json():
        client.delete(f"/students/{student['id']}", headers=headers)
    assert client.get("/students", headers=headers).headers["X-Total-Count"] == "115"
    assert client.post("/admin/reset-demo", headers=headers).status_code == 204
    assert client.get("/students", headers=headers).headers["X-Total-Count"] == "120"
    assert client.get("/allocation/runs", headers=headers).json()[0]["triggered_by"] == (
        "admin@demo.edu"
    )


def test_bootstrap_admin_from_environment(monkeypatch, client):
    monkeypatch.setattr(settings, "admin_email", "Owner@Uni.edu")
    monkeypatch.setattr(settings, "admin_password", "first-password")
    with SessionLocal() as db:
        bootstrap(db)
        # Changing the env password rotates it on the next boot.
        monkeypatch.setattr(settings, "admin_password", "second-password")
        bootstrap(db)
        assert db.query(User).filter(User.email == "owner@uni.edu").one().role == "admin"
    ok = client.post("/auth/login", json={"email": "owner@uni.edu", "password": "second-password"})
    old = client.post("/auth/login", json={"email": "owner@uni.edu", "password": "first-password"})
    assert ok.status_code == 200 and old.status_code == 401


@pytest.mark.parametrize(
    "url,expected",
    [
        ("postgres://u:p@h:5432/db", "postgresql+psycopg2://u:p@h:5432/db"),
        ("postgresql://u:p@h/db", "postgresql+psycopg2://u:p@h/db"),
        ("postgresql+psycopg2://u:p@h/db", "postgresql+psycopg2://u:p@h/db"),
        ("sqlite:///./x.db", "sqlite:///./x.db"),
    ],
)
def test_database_url_normalised_for_sqlalchemy(url, expected):
    assert Settings(database_url=url).database_url == expected


def test_production_requires_a_real_jwt_secret():
    with pytest.raises(ValidationError):
        Settings(environment="production", jwt_secret="short")
    with pytest.raises(ValidationError):
        Settings(environment="production", jwt_secret=_DEV_JWT_SECRET)
    assert Settings(environment="production", jwt_secret="x" * 32)


def test_cors_origin_list():
    s = Settings(cors_origins="https://a.app, https://b.app ,")
    assert s.cors_origin_list == ["https://a.app", "https://b.app"]


@pytest.mark.parametrize(
    "provider,key,expected",
    [
        ("auto", "k", "gemini"),
        ("auto", "", "none"),
        ("ollama", "", "ollama"),
        ("none", "k", "none"),
    ],
)
def test_llm_provider_selection(monkeypatch, provider, key, expected):
    monkeypatch.setattr(settings, "llm_provider", provider)
    monkeypatch.setattr(settings, "gemini_api_key", key)
    llm_module._configured_client.cache_clear()
    try:
        client = llm_module.get_llm()
        assert (client.provider if client else "none") == expected
    finally:
        llm_module._configured_client.cache_clear()


def test_explicit_gemini_without_key_disables_llm(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    llm_module._configured_client.cache_clear()
    try:
        assert llm_module.get_llm() is None
    finally:
        llm_module._configured_client.cache_clear()
