"""Authentication, authorization (roles) and login rate limiting."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import settings
from app.database import SessionLocal
from app.models import User
from app.routers.auth import login_limiter
from app.security import hash_password, verify_password

from .conftest import TEST_PASSWORD


def test_password_hash_roundtrip_and_salting():
    h1, h2 = hash_password("s3cret"), hash_password("s3cret")
    assert h1 != h2  # random salt
    assert verify_password("s3cret", h1)
    assert not verify_password("wrong", h1)
    assert not verify_password("s3cret", "garbage")


def test_login_returns_token_that_authenticates(client, make_user):
    make_user("viewer", email="Viewer@Test.edu")
    res = client.post("/auth/login", json={"email": "viewer@test.edu", "password": TEST_PASSWORD})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["token_type"] == "bearer"
    assert body["user"] == {
        "id": body["user"]["id"],
        "email": "viewer@test.edu",
        "full_name": "Viewer",
        "role": "viewer",
    }
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["email"] == "viewer@test.edu"


@pytest.mark.parametrize(
    "email,password",
    [("admin@test.edu", "wrong-password"), ("nobody@test.edu", TEST_PASSWORD)],
)
def test_login_rejects_bad_credentials_with_same_message(client, make_user, email, password):
    make_user("admin")
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 401
    assert res.json()["detail"] == "Incorrect email or password"


def test_inactive_user_cannot_log_in_or_use_token(client, make_user, admin_headers):
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == "admin@test.edu").one()
        user.is_active = False
        db.commit()
    res = client.post("/auth/login", json={"email": "admin@test.edu", "password": TEST_PASSWORD})
    assert res.status_code == 401
    assert client.get("/courses", headers=admin_headers).status_code == 401


def test_login_is_rate_limited(client, make_user, monkeypatch):
    make_user("admin")
    monkeypatch.setattr(login_limiter, "limit", 3)
    for _ in range(3):
        client.post("/auth/login", json={"email": "admin@test.edu", "password": "nope"})
    res = client.post("/auth/login", json={"email": "admin@test.edu", "password": TEST_PASSWORD})
    assert res.status_code == 429
    assert int(res.headers["Retry-After"]) >= 1


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/courses"),
        ("get", "/students"),
        ("get", "/allocation"),
        ("get", "/dashboard/stats"),
        ("post", "/assistant/query"),
        ("post", "/allocation/run"),
    ],
)
def test_data_endpoints_require_authentication(client, method, path):
    res = getattr(client, method)(path)
    assert res.status_code == 401
    assert res.headers["WWW-Authenticate"] == "Bearer"


def test_invalid_and_expired_tokens_rejected(client, make_user):
    user_id = make_user("admin")
    assert client.get("/courses", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401

    expired = jwt.encode(
        {"sub": str(user_id), "role": "admin", "exp": datetime.now(UTC) - timedelta(minutes=1)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    assert client.get("/courses", headers={"Authorization": f"Bearer {expired}"}).status_code == 401

    forged = jwt.encode(
        {"sub": str(user_id), "role": "admin", "exp": datetime.now(UTC) + timedelta(hours=1)},
        "some-other-secret-that-is-also-long-enough-000000",
        algorithm="HS256",
    )
    assert client.get("/courses", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/courses", {"name": "X", "total_seats": 1}),
        ("put", "/courses/1", {"total_seats": 3}),
        ("delete", "/courses/1", None),
        ("post", "/students", {"roll_no": "R", "name": "N", "marks": 1, "category_code": "SC"}),
        ("put", "/students/1", {"marks": 3}),
        ("delete", "/students/1", None),
        ("post", "/allocation/run", None),
        ("post", "/admin/reset-demo", None),
    ],
)
def test_viewer_cannot_modify_anything(client, viewer_headers, method, path, body):
    kwargs = {"headers": viewer_headers}
    if body is not None:
        kwargs["json"] = body
    assert getattr(client, method)(path, **kwargs).status_code == 403


def test_viewer_can_read_and_use_assistant(client, viewer_headers):
    assert client.get("/courses", headers=viewer_headers).status_code == 200
    assert client.get("/dashboard/stats", headers=viewer_headers).status_code == 200
    res = client.post(
        "/assistant/query",
        json={"question": "Category-wise allocation summary"},
        headers=viewer_headers,
    )
    assert res.status_code == 200
