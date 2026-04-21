from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://medhelp:medhelp_secret@localhost:5432/medhelpagent"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM
    OPENAI_API_KEY: str
    OPENAI_BASE_URL: str = "https://yunwu.ai/v1"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TEMPERATURE: float = 0.1

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"

    # App
    ENV: str = "development"
    APP_TITLE: str = "家庭健康双工作区 Agent Platform API"
    APP_VERSION: str = "2.0.0"
    AUTH_SECRET: str = "dev-auth-secret-change-me"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
