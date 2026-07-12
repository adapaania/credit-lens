"""LangGraph tools: SEC filing retrieval and Tavily web search."""

import json

from langchain_core.tools import tool
from tavily import TavilyClient

from app.config import get_settings
from app.retrieval.hybrid import retrieve
from app.retrieval.query_rewrite import rewrite_query

_tavily_client: TavilyClient | None = None


def _get_tavily_client() -> TavilyClient:
    global _tavily_client
    if _tavily_client is None:
        settings = get_settings()
        _tavily_client = TavilyClient(api_key=settings.tavily_api_key)
    return _tavily_client


@tool
def retrieve_filing(query: str, filing_id: str) -> str:
    """Retrieve excerpts from a company's SEC 10-K filing.

    Use this for ANY company-specific financial figure, risk factor, or
    disclosure. filing_id must be exactly the value given in the user's
    message, one of: boeing-2024-10k, lockheed-2024-10k, rtx-2024-10k.
    Returns a JSON object with a "chunks" list, each chunk carrying page,
    section, and text so the answer can be cited precisely.
    """
    try:
        chunks = retrieve(rewrite_query(query), filing_id=filing_id)
    except Exception as exc:  # noqa: BLE001 - network call at a system boundary
        return json.dumps({"error": f"Filing retrieval is temporarily unavailable: {exc}"})

    return json.dumps(
        {
            "chunks": [
                {
                    "filing_id": filing_id,
                    "page": chunk["page"],
                    "section": chunk["section"],
                    "text": chunk["text"],
                    "company": chunk["company"],
                    "fiscal_year": chunk["fiscal_year"],
                }
                for chunk in chunks
            ]
        }
    )


@tool
def tavily_search(query: str) -> str:
    """Search the web for current market, industry, or general context.

    Do not use this for a specific company's financial figures from their
    SEC filing - use retrieve_filing for that instead. This tool's results
    are external web data and must never be presented as if they came from
    a SEC filing.
    """
    try:
        results = _get_tavily_client().search(query, max_results=5)
    except Exception as exc:  # noqa: BLE001 - network call at a system boundary
        return json.dumps({"error": f"Web search is temporarily unavailable: {exc}"})
    return json.dumps(results)
