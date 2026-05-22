from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Postgres connection
    database_url: str = "postgresql://agent:agentpass@localhost:5432/salesagent"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"     # change to "phi3:mini" if low RAM
    ollama_temperature: float = 0.4

    # FastAPI
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    class Config:
        env_file = ".env"


settings = Settings()
