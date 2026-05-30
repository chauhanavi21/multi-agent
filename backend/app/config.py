from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Postgres
    database_url: str = "postgresql://agent:agentpass@localhost:5432/salesagent"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"            # standard tier
    ollama_cheap_model: str = "phi3:mini"        # cheap tier
    ollama_embed_model: str = "nomic-embed-text" # for semantic cache
    ollama_temperature: float = 0.4

    # FastAPI
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # JWT (Phase 3)
    jwt_secret: str = "dev-secret-change-me-in-production-please"
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 60 * 24 * 7

    # Bootstrap admin
    bootstrap_admin_email: str = "boss@local.dev"
    bootstrap_admin_password: str = "bosspass"

    # Phase 4 — cost / cache
    redis_url: str = "redis://localhost:6379/0"
    cache_similarity_threshold: float = 0.95
    cache_ttl_seconds: int = 60 * 60 * 24   # 24h

    anthropic_api_key: str = ""        # leave empty for local-only
    anthropic_haiku_model: str = "claude-haiku-4-5"
    anthropic_sonnet_model: str = "claude-sonnet-4-5"

    default_monthly_budget_usd: float = 5.0    # generous default for testing
    budget_soft_limit_pct: float = 80.0        # downgrade above this
    budget_hard_limit_pct: float = 100.0       # block above this

    class Config:
        env_file = ".env"


settings = Settings()
