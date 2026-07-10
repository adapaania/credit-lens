"""Minimal LangChain-compatible Embeddings wrapper around our Cohere client.

Ragas expects a LangChain-style Embeddings object; this lets it use the same
embedding provider as the rest of the app instead of pulling in a second one.
"""

from langchain_core.embeddings import Embeddings

from app.ingestion.embeddings import embed_documents, embed_query


class CohereLangchainEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return embed_query(text)
