from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    secret_key: str = "change_me"
    cors_origins: str = "http://localhost:3000"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "court_search"
    postgres_user: str = "court_admin"
    postgres_password: str = "change_me"
    s3_bucket: str = "indian-supreme-court-judgments"
    aws_default_region: str = "ap-south-1"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    chunk_size: int = 800
    chunk_overlap: int = 100
    embedding_model: str = "text-embedding-3-small"
    embedding_batch_size: int = 100
    max_workers: int = 4
    top_k_results: int = 10
    hybrid_alpha: float = 0.6
    rag_model: str = "claude-sonnet-4-6"
    rag_max_tokens: int = 2000
    redis_url: str = "redis://localhost:6379/0"

    @property
    def database_url(self):
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

@lru_cache
def get_settings():
    return Settings()
