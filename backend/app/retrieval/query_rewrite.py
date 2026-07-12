"""Rewrite a natural-language question into a short retrieval query.

Diagnosed failure this fixes: raw questions like "What were Boeing's total
current assets at the end of fiscal year 2024?" are mostly filler words
("what were", "at the end of", "fiscal year 2024") that appear in nearly
every chunk of a 10-K. That dilutes both BM25 term-weighting and dense-
embedding similarity enough that the correct balance-sheet chunk (e.g. the
one containing "Total current assets 127,998") never reaches the top 20
candidates for either retriever, even though it is indexed. A short,
targeted query like "total current assets" retrieves that same chunk at
rank 0. `backend/app/memo.py` already sidesteps this by hand-writing short
queries per figure (see FIGURE_QUERIES) - this module generalizes that
fix to arbitrary user questions instead of a fixed set of six figures.
"""

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import get_settings

REWRITE_PROMPT = """Rewrite the user's question as a short search query (3-8 words) using the exact financial-statement terminology it is asking about. Drop filler words, company names, and dates. Output only the search query, nothing else.

Examples:
"What was Boeing's total consolidated revenue in fiscal year 2024?" -> total revenue total revenues consolidated
"What were Boeing's total current assets at the end of fiscal year 2024?" -> total current assets
"What liquidity risks did Boeing disclose?" -> liquidity risk"""

_model: ChatOpenAI | None = None


def _get_model() -> ChatOpenAI:
    global _model
    if _model is None:
        settings = get_settings()
        _model = ChatOpenAI(
            model=settings.chat_model,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            temperature=0,
            max_tokens=32,
        )
    return _model


def rewrite_query(question: str) -> str:
    """Best-effort query rewrite; falls back to the original question on any error."""
    try:
        response = _get_model().invoke(
            [SystemMessage(content=REWRITE_PROMPT), HumanMessage(content=question)]
        )
        rewritten = (response.content or "").strip()
        return rewritten or question
    except Exception:  # noqa: BLE001 - network call at a system boundary
        return question
