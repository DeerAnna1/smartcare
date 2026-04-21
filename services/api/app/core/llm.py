from openai import AsyncOpenAI
from functools import lru_cache
from app.core.config import get_settings


@lru_cache
def get_llm_client() -> AsyncOpenAI:
    settings = get_settings()
    return AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
    )
