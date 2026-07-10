"""Embedding client.

OpenRouter has no embeddings endpoint, so per the project's hard requirement
that embeddings may be isolated in one swappable module, this is that module.
Everything else (index.py, retrieval/dense.py) imports from here rather than
calling Cohere directly, so the provider can be swapped in one place.
"""

import time

import cohere

from app.config import get_settings

_client: cohere.Client | None = None

_MAX_ATTEMPTS = 4
_BACKOFF_SECONDS = 1.5


def _get_client() -> cohere.Client:
    global _client
    if _client is None:
        settings = get_settings()
        _client = cohere.Client(settings.cohere_api_key)
    return _client


def _with_retry(call):
    """Retry on transient connection errors (observed intermittent local DNS
    flakiness to Cohere's API), not on real API errors like bad auth."""
    last_error: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return call()
        except cohere.errors.unauthorized_error.UnauthorizedError:
            raise
        except Exception as exc:  # noqa: BLE001 - network call at a system boundary
            last_error = exc
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_BACKOFF_SECONDS * (attempt + 1))
    raise last_error


def embed_documents(texts: list[str]) -> list[list[float]]:
    settings = get_settings()
    response = _with_retry(
        lambda: _get_client().embed(
            texts=texts,
            model=settings.embedding_model,
            input_type="search_document",
            truncate="END",
        )
    )
    return list(response.embeddings)


def embed_query(text: str) -> list[float]:
    settings = get_settings()
    response = _with_retry(
        lambda: _get_client().embed(
            texts=[text],
            model=settings.embedding_model,
            input_type="search_query",
            truncate="END",
        )
    )
    return list(response.embeddings[0])
