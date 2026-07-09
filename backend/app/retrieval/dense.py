"""Naive dense retrieval: top-k 8 similarity search filtered by filing_id."""

from typing import TypedDict

from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.config import get_settings
from app.ingestion.embeddings import embed_query
from app.ingestion.index import get_qdrant_client


class RetrievedChunk(TypedDict):
    score: float
    page: int
    section: str
    text: str
    company: str
    fiscal_year: int


def retrieve(query: str, filing_id: str, top_k: int | None = None) -> list[RetrievedChunk]:
    settings = get_settings()
    client = get_qdrant_client()
    vector = embed_query(query)

    results = client.query_points(
        collection_name=settings.qdrant_collection,
        query=vector,
        query_filter=Filter(
            must=[FieldCondition(key="filing_id", match=MatchValue(value=filing_id))]
        ),
        limit=top_k or settings.dense_top_k,
        with_payload=True,
    )

    return [
        {
            "score": point.score,
            "page": point.payload["page"],
            "section": point.payload["section"],
            "text": point.payload["text"],
            "company": point.payload["company"],
            "fiscal_year": point.payload["fiscal_year"],
        }
        for point in results.points
    ]
