from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.database import engine, Base
from app.api.v1 import api_router
from app.jobs.proactive_intervention import run_once as run_proactive_once
from app.core.observability import init_langfuse, flush_langfuse

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Langfuse observability
    init_langfuse()

    # 当前仓库仍保留历史自动建表能力，用于开发环境快速启动。
    # 生产/正式环境应优先使用 Alembic 管理 schema。
    if settings.should_auto_create_tables:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    proactive_task: asyncio.Task | None = None
    async def proactive_loop():
        while True:
            try:
                await run_proactive_once()
            except Exception:
                pass
            await asyncio.sleep(1800)

    if settings.PROACTIVE_JOB_ENABLED:
        proactive_task = asyncio.create_task(proactive_loop())
    yield
    if proactive_task:
        proactive_task.cancel()
    # Flush Langfuse events before shutdown
    flush_langfuse()
    await engine.dispose()


app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}
