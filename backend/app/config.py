from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://agent:agentpass@localhost:5432/salesagent"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_cheap_model: str = "phi3:mini"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_temperature: float = 0.4
    ollama_timeout_s: float = 180.0

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    jwt_secret: str = "dev-secret-change-me-in-production-please"
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 60 * 24 * 7

    bootstrap_admin_email: str = "boss@local.dev"
    bootstrap_admin_password: str = "bosspass"

    redis_url: str = "redis://localhost:6379/0"
    cache_similarity_threshold: float = 0.95
    cache_ttl_seconds: int = 60 * 60 * 24

    anthropic_api_key: str = ""
    anthropic_haiku_model: str = "claude-haiku-4-5"
    anthropic_sonnet_model: str = "claude-sonnet-4-5"

    bedrock_region: str = "us-east-1"
    bedrock_haiku_model_id: str = "anthropic.claude-haiku-4-5-20251001-v1:0"
    bedrock_sonnet_model_id: str = "anthropic.claude-sonnet-4-5-20250929-v1:0"

    default_monthly_budget_usd: float = 5.0
    budget_soft_limit_pct: float = 80.0
    budget_hard_limit_pct: float = 100.0

    default_cloud_provider: str = "anthropic"

    # ===== Phase 6 =====
    # Twilio (SMS). If not set, sms_tools mocks the send.
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""

    # Apify (Instagram/Facebook reel scraping). If not set, competitor_reels uses mock.
    apify_token: str = ""
    apify_instagram_actor: str = "apify/instagram-scraper"

    # Scheduler — process-global on/off. Per-company toggle is in companies.scheduler_enabled.
    scheduler_enabled: bool = True
    # Where APScheduler should run jobs. 'in_process' is simplest; 'disabled' = manual only.
    scheduler_mode: str = "in_process"   # in_process | disabled

    # Memory tuning
    memory_min_similarity: float = 0.55
    memory_top_k_for_retrieval: int = 5

    # Stripe billing (optional — leave empty for local-only billing via admin)
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id_pro: str = ""
    stripe_price_id_team: str = ""
    frontend_base_url: str = "http://localhost:5173"

    class Config:
        env_file = ".env"


settings = Settings()
