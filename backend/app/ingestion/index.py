"""Index chunked 10-K filings into a single Qdrant collection."""

import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from app.config import get_settings
from app.ingestion.chunk import Chunk
from app.ingestion.embeddings import embed_documents

_client: QdrantClient | None = None


def get_qdrant_client() -> QdrantClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=60)
    return _client


def ensure_collection() -> None:
    settings = get_settings()
    client = get_qdrant_client()
    existing = {c.name for c in client.get_collections().collections}
    if settings.qdrant_collection not in existing:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=settings.embedding_dim, distance=Distance.COSINE),
        )
    # Idempotent: safe to call even if the index already exists.
    client.create_payload_index(
        collection_name=settings.qdrant_collection,
        field_name="filing_id",
        field_schema=PayloadSchemaType.KEYWORD,
    )


def _point_id(filing_id: str, page: int, position: int) -> str:
    # Deterministic UUID so re-ingesting the same filing overwrites in place
    # instead of duplicating points.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"creditlens:{filing_id}:{page}:{position}"))


def delete_filing(filing_id: str) -> None:
    """Remove all existing points for a filing_id before re-ingesting it."""
    settings = get_settings()
    client = get_qdrant_client()
    existing = {c.name for c in client.get_collections().collections}
    if settings.qdrant_collection not in existing:
        return
    ensure_collection()
    client.delete(
        collection_name=settings.qdrant_collection,
        points_selector=Filter(
            must=[FieldCondition(key="filing_id", match=MatchValue(value=filing_id))]
        ),
    )


def index_chunks(
    chunks: list[Chunk],
    filing_id: str,
    company: str,
    fiscal_year: int,
    batch_size: int = 16,
) -> int:
    """Embed and upsert chunks into Qdrant. Returns the number of points written."""
    ensure_collection()
    client = get_qdrant_client()
    settings = get_settings()

    total = 0
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        vectors = embed_documents([c["text"] for c in batch])
        points = [
            PointStruct(
                id=_point_id(filing_id, chunk["page"], start + offset),
                vector=vector,
                payload={
                    "filing_id": filing_id,
                    "company": company,
                    "fiscal_year": fiscal_year,
                    "section": chunk["section"],
                    "page": chunk["page"],
                    "text": chunk["text"],
                },
            )
            for offset, (chunk, vector) in enumerate(zip(batch, vectors))
        ]
        client.upsert(collection_name=settings.qdrant_collection, points=points)
        total += len(points)
    return total
