from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Postgres
    database_url: str = "postgresql://agent:agentpass@localhost:5432/salesagent"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_temperature: float = 0.4

    # FastAPI
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # JWT (Phase 3)
    jwt_secret: str = "dev-secret-change-me-in-production-please"
    jwt_algorithm: str = "HS256"
    jwt_ttl_minutes: int = 60 * 24 * 7   # 7 days

    # Bootstrap admin (only used by bootstrap_admin.py)
    bootstrap_admin_email: str = "boss@local.dev"
    bootstrap_admin_password: str = "bosspass"

    class Config:
        env_file = ".env"


settings = Settings()
