"""Health check, public app metadata, and demo administration."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .. import __version__, models, schemas
from ..auth import require_admin
from ..config import settings
from ..database import get_db
from ..llm import get_llm
from ..seed import DEMO_ACCOUNTS, DEMO_PASSWORD, reset_demo

router = APIRouter(tags=["meta"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    """Liveness + database connectivity (used by the platform health check)."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "down"})
    return {"status": "ok", "database": "ok"}


@router.get("/meta", response_model=schemas.MetaOut)
def meta():
    """Public, unauthenticated facts the UI needs before sign-in."""
    llm = get_llm()
    return schemas.MetaOut(
        version=__version__,
        environment=settings.environment,
        demo_mode=settings.demo_mode,
        llm_provider=llm.provider if llm else "none",
        llm_model=llm.model if llm else None,
        demo_accounts=[
            schemas.DemoAccount(email=email, password=DEMO_PASSWORD, role=role)
            for email, _, role in DEMO_ACCOUNTS
        ]
        if settings.demo_mode
        else [],
    )


@router.post("/admin/reset-demo", status_code=204, tags=["admin"])
def reset_demo_data(admin: models.User = Depends(require_admin), db: Session = Depends(get_db)):
    """Reload the sample dataset and re-run allocation. Demo mode only."""
    if not settings.demo_mode:
        raise HTTPException(status_code=404, detail="Not available outside demo mode")
    reset_demo(db, triggered_by=admin.email)
