from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Postgres
    database_url: str = "postgresql://agent:agentpass@localhost:5432/salesagent"

    # Ollama — base_url can point at localhost OR a Tailscale tunnel.
    # Example for production-from-home: OLLAMA_BASE_URL=http://100.64.x.y:11434
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_cheap_model: str = "phi3:mini"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_temperature: float = 0.4
    ollama_timeout_s: float = 180.0

    # FastAPI
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # JWT
    jwt_secret: str = "dev-secret-change-me-in-production-please"
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 60 * 24 * 7

    # Bootstrap admin
    bootstrap_admin_email: str = "boss@local.dev"
    bootstrap_admin_password: str = "bosspass"

    # Cost / cache (Phase 4)
    redis_url: str = "redis://localhost:6379/0"
    cache_similarity_threshold: float = 0.95
    cache_ttl_seconds: int = 60 * 60 * 24

    # Anthropic direct
    anthropic_api_key: str = ""
    anthropic_haiku_model: str = "claude-haiku-4-5"
    anthropic_sonnet_model: str = "claude-sonnet-4-5"

    # AWS Bedrock (Phase 5) — IAM-based, no key needed when running on EC2 with role
    bedrock_region: str = "us-east-1"
    bedrock_haiku_model_id: str = "anthropic.claude-haiku-4-5-20251001-v1:0"
    bedrock_sonnet_model_id: str = "anthropic.claude-sonnet-4-5-20250929-v1:0"

    default_monthly_budget_usd: float = 5.0
    budget_soft_limit_pct: float = 80.0
    budget_hard_limit_pct: float = 100.0

    # Phase 5
    # Default cloud provider for new companies. Per-company override lives in DB.
    default_cloud_provider: str = "anthropic"   # 'anthropic' | 'bedrock'

    class Config:
        env_file = ".env"


settings = Settings()
