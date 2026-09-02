"""AI assistant endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..ai_assistant import answer_question
from ..auth import require_api_key
from ..database import get_db

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post(
    "/query", response_model=schemas.AssistantResponse, dependencies=[Depends(require_api_key)]
)
def query(payload: schemas.AssistantQuery, db: Session = Depends(get_db)):
    result = answer_question(db, payload.question)
    return schemas.AssistantResponse(question=payload.question, **result)
