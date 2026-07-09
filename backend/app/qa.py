"""Phase 1 retrieve-then-answer flow.

This is intentionally a plain function, not an agent: LangGraph and tool
choice (filing retrieval vs. Tavily) are introduced in Phase 2.
"""

from typing import TypedDict

from openai import OpenAI

from app.agent.prompts import ANSWER_SYSTEM_PROMPT, build_answer_user_prompt
from app.config import get_settings
from app.retrieval.dense import retrieve

_client: OpenAI | None = None


class Citation(TypedDict):
    page: int
    section: str
    snippet: str


class Answer(TypedDict):
    answer: str
    citations: list[Citation]


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        _client = OpenAI(api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url)
    return _client


def answer_question(question: str, filing_id: str) -> Answer:
    chunks = retrieve(question, filing_id=filing_id)

    if not chunks:
        return {
            "answer": (
                "No indexed content was found for this filing. "
                "Run `python scripts/ingest.py` before asking questions."
            ),
            "citations": [],
        }

    settings = get_settings()
    response = _get_client().chat.completions.create(
        model=settings.chat_model,
        messages=[
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {"role": "user", "content": build_answer_user_prompt(question, chunks)},
        ],
        temperature=0,
    )
    answer_text = response.choices[0].message.content or ""

    citations: list[Citation] = [
        {"page": chunk["page"], "section": chunk["section"], "snippet": chunk["text"][:300]}
        for chunk in chunks
    ]
    return {"answer": answer_text, "citations": citations}
