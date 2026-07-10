"""Shared retrieve -> answer pipeline for eval comparison.

Deliberately not the LangGraph agent from Phase 2: the agent's Tavily/
tool-choice behavior is a separate concern from retrieval quality, and
Phase 4 is specifically about comparing retrieval methods (naive dense vs
hybrid) with everything else held constant.
"""

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import get_settings

ANSWER_PROMPT = """You are CreditLens, answering a credit analyst's question using only the provided SEC filing excerpts.

Every financial figure in your answer must be immediately followed by its citation in the format (page N, section). If the excerpts do not contain a figure needed to answer, say so explicitly instead of estimating it. Never estimate or infer a figure that is not present in the excerpts."""

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
        )
    return _model


def answer_with_retrieval(question: str, filing_id: str, retrieve_fn) -> dict:
    chunks = retrieve_fn(question, filing_id=filing_id)
    context = "\n\n---\n\n".join(
        f"[page {chunk['page']}, section: {chunk['section']}]\n{chunk['text']}" for chunk in chunks
    )
    response = _get_model().invoke(
        [
            SystemMessage(content=ANSWER_PROMPT),
            HumanMessage(content=f"Filing excerpts:\n\n{context}\n\nQuestion: {question}"),
        ]
    )
    return {
        "answer": response.content or "",
        "contexts": [chunk["text"] for chunk in chunks],
        "citations": [{"page": chunk["page"], "section": chunk["section"]} for chunk in chunks],
    }
