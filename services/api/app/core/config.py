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
    AUTO_CREATE_TABLES: bool | None = None
    APP_TITLE: str = "家庭健康双工作区 Agent Platform API"
    APP_VERSION: str = "2.0.0"
    AUTH_SECRET: str = "dev-auth-secret-change-me"
    WEBHOOK_SECRET: str = "dev-webhook-secret-change-me"
    OCR_PROVIDER: str = "builtin"
    OCR_API_KEY: str = ""
    WEATHER_API_BASE: str = "https://api.open-meteo.com/v1/forecast"
    WEATHER_API_KEY: str = ""
    DEFAULT_USER_CITY: str = "beijing"
    PROACTIVE_JOB_ENABLED: bool = False
    IOT_WEBHOOK_HMAC_SECRET: str = "dev-iot-hmac-secret-change-me"
    IOT_WEBHOOK_MAX_SKEW_SECONDS: int = 300

    # Langfuse Observability
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"
    LANGFUSE_ENABLED: bool = False

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    @property
    def should_auto_create_tables(self) -> bool:
        if self.AUTO_CREATE_TABLES is not None:
            return self.AUTO_CREATE_TABLES
        return self.ENV == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
