"""AI assistant endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..ai_assistant import answer_question
from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..llm import LLMClient, get_llm
from ..ratelimit import RateLimiter

router = APIRouter(prefix="/assistant", tags=["assistant"])

assistant_limiter = RateLimiter(settings.assistant_rate_limit)


@router.post("/query", response_model=schemas.AssistantResponse)
def query(
    payload: schemas.AssistantQuery,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
    llm: LLMClient | None = Depends(get_llm),
):
    """Ask a question in plain English; get an answer plus the SQL and rows behind it."""
    assistant_limiter.hit(f"assistant:{user.id}")
    result = answer_question(db, payload.question, llm)
    return schemas.AssistantResponse(question=payload.question, **result)
