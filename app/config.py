"""Settings loaded from environment variables (and .env)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://rag:rag@127.0.0.1:5432/annual_reports"

    groq_api_key: str = ""
    anthropic_api_key: str = ""
    # Cheapest general chat model on Groq (Nov 2026); override in .env to compare models.
    groq_model: str = "openai/gpt-oss-20b"
    # Fallback when Groq's free-tier daily limit is hit: the cheapest current Claude model.
    anthropic_model: str = "claude-haiku-5-5"
    llm_cache_dir: Path = ROOT / ".cache" / "llm"
    retrieval_k: int = 5
    reranker_model: str = "BAAI/bge-reranker-base"

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384

    raw_dir: Path = ROOT / "data" / "raw"
    processed_dir: Path = ROOT / "data" / "processed"


@lru_cache
def get_settings() -> Settings:
    return Settings()
