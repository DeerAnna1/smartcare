from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://medhelp:medhelp_secret@localhost:5432/medhelpagent"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM (MiMo model family — OpenAI-compatible API)
    OPENAI_API_KEY: str
    OPENAI_BASE_URL: str = "https://token-plan-cn.xiaomimimo.com/v1"
    LLM_MODEL: str = "mimo-v2-omni"  # Multimodal: image + video + text
    LLM_TEMPERATURE: float = 0.1

    # MiMo model variants
    MIMO_ASR_MODEL: str = "mimo-v2.5-asr"       # Speech-to-text
    MIMO_TTS_MODEL: str = "mimo-v2.5-tts"       # Text-to-speech
    MIMO_OMNI_MODEL: str = "mimo-v2-omni"       # Multimodal (vision + text)

    # Whisper / ASR
    WHISPER_MODEL: str = "mimo-v2.5-asr"
    WHISPER_BASE_URL: str = ""  # If empty, uses OPENAI_BASE_URL

    # TTS
    TTS_MODEL: str = "mimo-v2.5-tts"
    TTS_BASE_URL: str = ""  # If empty, uses OPENAI_BASE_URL

    # Multimodal upload limits
    MAX_VIDEO_SIZE: int = 100 * 1024 * 1024  # 100MB for video

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

    # Sentry / Logging
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    # DB pool
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 1800
    DB_POOL_TIMEOUT: int = 30

    # LLM 重试 / 超时
    LLM_REQUEST_TIMEOUT: int = 30
    LLM_MAX_RETRIES: int = 2

    # RAG
    RAG_EMBEDDING_MODEL: str = "BAAI/bge-large-zh-v1.5"  # 中文嵌入模型（1024维，检索 SOTA）
    RAG_CHUNK_SIZE: int = 400
    RAG_CHUNK_OVERLAP: int = 50
    RAG_SCORE_THRESHOLD: float = 0.35
    RAG_USE_MMR: bool = True
    RAG_RERANKER_ENABLED: bool = False
    RAG_RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"  # Cross-Encoder 重排模型
    RAG_RERANKER_TOP_K: int = 3  # 重排后保留的文档数

    # Memory window
    MEMORY_TOKEN_BUDGET: int = 3000
    MEMORY_RECENT_TURNS: int = 6

    # Concurrency control (性能优化)
    CONCURRENCY_ENABLED: bool = True
    CONCURRENCY_MAX_CONCURRENT_REQUESTS: int = 30      # 每 worker 最大并发请求数
    CONCURRENCY_MAX_CONCURRENT_LLM_CALLS: int = 15     # 每 worker 最大并发 LLM 调用数
    CONCURRENCY_RAG_THREAD_POOL_SIZE: int = 8          # RAG 线程池大小
    CONCURRENCY_LLM_ACQUIRE_TIMEOUT: int = 30          # LLM 信号量获取超时(秒)

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
