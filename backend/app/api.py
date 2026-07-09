from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config import get_settings


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
    filing_context = f" for filing `{request.filing_id}`" if request.filing_id else ""
    thread_context = f" on thread `{request.thread_id}`" if request.thread_id else ""
    return ChatResponse(
        answer=f"Echo{filing_context}{thread_context}: {request.message}",
        citations=[],
    )
