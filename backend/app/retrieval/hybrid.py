"""Hybrid retrieval: dense (Cohere embeddings) + BM25, fused with reciprocal
rank fusion, reranked from top-20 to top-6 with Cohere Rerank.

This is the Phase 4 comparison target for naive dense retrieval
(backend/app/retrieval/dense.py). Both share the same underlying Qdrant
collection - hybrid only adds a BM25 signal and a rerank pass on top.
"""

import re

import cohere
from qdrant_client.models import FieldCondition, Filter, MatchValue
from rank_bm25 import BM25Okapi

from app.config import get_settings
from app.ingestion.index import get_qdrant_client
from app.retrieval.dense import RetrievedChunk
from app.retrieval.dense import retrieve as dense_retrieve

RRF_K = 60
DENSE_CANDIDATES = 20
BM25_CANDIDATES = 20
FUSED_CANDIDATES = 20

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_corpus_cache: dict[str, tuple[list[dict], BM25Okapi]] = {}
_cohere_client: cohere.Client | None = None


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _chunk_key(chunk: dict) -> tuple:
    return (chunk["page"], chunk["section"], chunk["text"])


def _get_cohere_client() -> cohere.Client:
    global _cohere_client
    if _cohere_client is None:
        settings = get_settings()
        _cohere_client = cohere.Client(settings.cohere_api_key)
    return _cohere_client


def _load_corpus(filing_id: str) -> tuple[list[dict], BM25Okapi]:
    """Fetch every chunk for filing_id from Qdrant and build a BM25 index over it.

    Cached per filing_id for the life of the process - filings don't change
    during a run, and the largest corpus here is under 500 chunks, so a
    single unpaginated scroll comfortably covers it.
    """
    if filing_id in _corpus_cache:
        return _corpus_cache[filing_id]

    settings = get_settings()
    client = get_qdrant_client()
    records, _ = client.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=Filter(must=[FieldCondition(key="filing_id", match=MatchValue(value=filing_id))]),
        limit=2000,
        with_payload=True,
        with_vectors=False,
    )
    chunks = [
        {
            "page": record.payload["page"],
            "section": record.payload["section"],
            "text": record.payload["text"],
            "company": record.payload["company"],
            "fiscal_year": record.payload["fiscal_year"],
        }
        for record in records
    ]
    bm25 = BM25Okapi([_tokenize(chunk["text"]) for chunk in chunks])
    _corpus_cache[filing_id] = (chunks, bm25)
    return chunks, bm25


def _bm25_ranking(query: str, filing_id: str, top_k: int = BM25_CANDIDATES) -> list[dict]:
    chunks, bm25 = _load_corpus(filing_id)
    if not chunks:
        return []
    scores = bm25.get_scores(_tokenize(query))
    ranked_indices = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)[:top_k]
    return [chunks[i] for i in ranked_indices]


def _reciprocal_rank_fusion(
    dense_ranking: list[dict], bm25_ranking: list[dict], k: int = RRF_K
) -> list[dict]:
    scores: dict[tuple, float] = {}
    chunk_by_key: dict[tuple, dict] = {}
    for ranking in (dense_ranking, bm25_ranking):
        for rank, chunk in enumerate(ranking):
            key = _chunk_key(chunk)
            chunk_by_key.setdefault(key, chunk)
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
    ranked_keys = sorted(scores, key=lambda key: scores[key], reverse=True)
    return [chunk_by_key[key] for key in ranked_keys]


def _rerank(query: str, chunks: list[dict], top_n: int) -> list[tuple[dict, float]]:
    if not chunks:
        return []
    settings = get_settings()
    response = _get_cohere_client().rerank(
        query=query,
        documents=[chunk["text"] for chunk in chunks],
        model=settings.rerank_model,
        top_n=min(top_n, len(chunks)),
    )
    return [(chunks[result.index], result.relevance_score) for result in response.results]


def retrieve(query: str, filing_id: str, top_k: int | None = None) -> list[RetrievedChunk]:
    settings = get_settings()
    dense_ranking = dense_retrieve(query, filing_id=filing_id, top_k=DENSE_CANDIDATES)
    bm25_ranking = _bm25_ranking(query, filing_id=filing_id, top_k=BM25_CANDIDATES)
    fused = _reciprocal_rank_fusion(dense_ranking, bm25_ranking)[:FUSED_CANDIDATES]
    reranked = _rerank(query, fused, top_n=top_k or settings.hybrid_top_k)

    return [
        {
            "score": relevance_score,
            "page": chunk["page"],
            "section": chunk["section"],
            "text": chunk["text"],
            "company": chunk["company"],
            "fiscal_year": chunk["fiscal_year"],
        }
        for chunk, relevance_score in reranked
    ]
