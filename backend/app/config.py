from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CreditLens API"
    environment: str = "development"
    frontend_origin: str = "http://localhost:3000"

    openrouter_api_key: str | None = None
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    tavily_api_key: str | None = None
    langchain_tracing_v2: str | None = None
    langchain_api_key: str | None = None
    langchain_project: str = "creditlens"
    cohere_api_key: str | None = None

    qdrant_collection: str = "creditlens_filings"
    embedding_model: str = "embed-english-v3.0"
    embedding_dim: int = 1024
    dense_top_k: int = 8

    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    chat_model: str = "openai/gpt-4.1-mini"
    rerank_model: str = "rerank-v3.5"
    hybrid_top_k: int = 6

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins(self) -> List[str]:
        origins = {
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            self.frontend_origin.rstrip("/"),
        }
        return sorted(origin for origin in origins if origin)


@lru_cache
def get_settings() -> Settings:
    return Settings()
