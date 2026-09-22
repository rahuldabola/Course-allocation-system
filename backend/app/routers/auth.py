"""Login and current-user endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..ratelimit import RateLimiter
from ..security import DUMMY_PASSWORD_HASH, create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

login_limiter = RateLimiter(settings.login_rate_limit)


def client_ip(request: Request) -> str:
    # uvicorn runs with --proxy-headers, so behind a platform proxy this is
    # the originating client address rather than the proxy's.
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=schemas.TokenOut)
def login(payload: schemas.LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Exchange email + password for a JWT access token."""
    login_limiter.hit(f"login:{client_ip(request)}")
    user = db.query(models.User).filter(models.User.email == payload.email.lower()).first()
    # Always run a hash comparison so timing doesn't reveal whether the email exists.
    password_ok = verify_password(
        payload.password, user.password_hash if user else DUMMY_PASSWORD_HASH
    )
    if user is None or not password_ok or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password"
        )
    token, expires_in = create_access_token(user.id, user.role)
    return schemas.TokenOut(
        access_token=token, expires_in=expires_in, user=schemas.UserOut.model_validate(user)
    )


@router.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user
