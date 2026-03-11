from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────────────────────
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "graphrag"
    postgres_user: str = "graphrag"
    postgres_password: str  # required — no default

    # ── Embeddings ────────────────────────────────────────────────────────────
    # BAAI/bge-m3 → 1024-dim, high quality, asymmetric retrieval
    # If you change this to a model with different output dimensions, you must
    # also update the vector(1024) column in 02_schema.sql and recreate the DB.
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "cuda"   # "cpu" for CPU-only environments
    embedding_batch_size: int = 32

    # ── Watcher ───────────────────────────────────────────────────────────────
    docs_path: str = "/docs"
    watch_recursive: bool = True

    # ── MCP server ────────────────────────────────────────────────────────────
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8000

    # ── Search defaults ───────────────────────────────────────────────────────
    search_top_k: int = 10
    search_min_score: float = 0.0

    # ── Enricher ──────────────────────────────────────────────────────────────
    # OpenAI-compatible endpoint (LiteLLM, vLLM, Ollama, …)
    enricher_base_url: str = "http://localhost:4000/v1"
    enricher_api_key: str = "dummy"          # local inference needs no real key
    enricher_model: str = "mistral/mistral-small-24b"
    enricher_concurrency: int = 4            # parallel LLM requests
    similar_to_threshold: float = 0.82       # cosine similarity cutoff
    similar_to_max_per_chunk: int = 5        # max SIMILAR_TO edges per chunk

    @field_validator("embedding_device")
    @classmethod
    def validate_device(cls, v: str) -> str:
        if v not in {"cuda", "cpu", "mps"}:
            raise ValueError("embedding_device must be 'cuda', 'cpu', or 'mps'")
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Module-level singleton — import and use directly
settings = Settings()  # type: ignore[call-arg]
