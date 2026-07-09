from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.qa import answer_question


router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    filing_id: str | None = None
    thread_id: str | None = None


class Citation(BaseModel):
    page: int | None = None
    section: str | None = None
    snippet: str | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation] = []


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    if not request.filing_id:
        raise HTTPException(status_code=400, detail="filing_id is required")

    result = answer_question(request.message, filing_id=request.filing_id)
    return ChatResponse(answer=result["answer"], citations=result["citations"])
