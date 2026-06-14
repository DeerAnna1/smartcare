from contextlib import asynccontextmanager
import asyncio
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from slowapi.errors import RateLimitExceeded
from app.core.rate_limit import limiter
from app.core.config import get_settings
from app.core.database import engine, Base, AsyncSessionLocal
from app.core.logging_config import configure_logging, init_sentry
from app.api.v1 import api_router
from app.jobs.proactive_intervention import run_once as run_proactive_once
from app.core.observability import init_langfuse, flush_langfuse

configure_logging()
init_sentry()

logger = logging.getLogger(__name__)
settings = get_settings()


def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "请求过于频繁，请稍后再试", "retry_after": exc.detail},
    )


DEFAULT_SKILLS = [
    {
        "skill_id": "drug-interaction",
        "name": "药物相互作用查询",
        "description": "查询药物之间的相互作用，返回相互作用等级、描述和用药建议",
        "category": "健康工具",
        "keywords": '["药物相互作用","药物冲突","用药安全","药品禁忌","drug interaction"]',
        "trigger_examples": '["这两种药能一起吃吗","阿莫西林和布洛芬有冲突吗","查一下药物相互作用"]',
        "tools": '[]',
        "source_type": "builtin",
        "version": "1.0.0",
    },
    {
        "skill_id": "appointment-booking",
        "name": "挂号预约",
        "description": "查询医生排班并预约挂号，支持按科室、医院和日期筛选",
        "category": "健康工具",
        "keywords": '["挂号","预约","看医生","门诊","appointment","booking"]',
        "trigger_examples": '["帮我挂一个心内科的号","明天有骨科医生吗","预约一个内科门诊"]',
        "tools": '[]',
        "source_type": "builtin",
        "version": "1.0.0",
    },
]


async def _seed_default_skills():
    """确保默认技能包存在于数据库中（幂等 upsert）。"""
    from sqlalchemy import select
    from app.models.models import SkillPackage

    try:
        async with AsyncSessionLocal() as db:
            for skill_data in DEFAULT_SKILLS:
                existing = await db.execute(
                    select(SkillPackage).where(SkillPackage.skill_id == skill_data["skill_id"])
                )
                if existing.scalar_one_or_none() is None:
                    db.add(SkillPackage(**skill_data))
            await db.commit()
            logger.info("默认技能包检查完成")
    except Exception:
        logger.exception("默认技能包种植失败")


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
                logger.exception("proactive_loop iteration failed")
            await asyncio.sleep(1800)

    if settings.PROACTIVE_JOB_ENABLED:
        proactive_task = asyncio.create_task(proactive_loop())

    # 种植默认技能包（确保药物相互作用和挂号预约始终可用）
    await _seed_default_skills()

    # 预热 Redis（快速，阻塞启动可接受）
    try:
        from app.services.context_manager import _get_redis
        await _get_redis()
        logger.info("Redis 预热完成")
    except Exception:
        logger.warning("Redis 预热失败，首次请求可能较慢")

    # 初始化并发控制（信号量 + 线程池）
    from app.core.concurrency import init_concurrency
    init_concurrency(
        max_requests=settings.CONCURRENCY_MAX_CONCURRENT_REQUESTS if settings.CONCURRENCY_ENABLED else 9999,
        max_llm_calls=settings.CONCURRENCY_MAX_CONCURRENT_LLM_CALLS if settings.CONCURRENCY_ENABLED else 9999,
        rag_pool_size=settings.CONCURRENCY_RAG_THREAD_POOL_SIZE,
    )

    # 预热 ChromaDB 和重排模型（可能需下载模型，后台执行不阻塞启动）
    async def _warm_chromadb():
        try:
            from app.services.rag_retriever import _get_collection, _get_reranker
            await asyncio.to_thread(_get_collection)
            logger.info("ChromaDB 预热完成")
            if settings.RAG_RERANKER_ENABLED:
                reranker = await asyncio.to_thread(_get_reranker)
                if reranker:
                    await asyncio.to_thread(reranker._load_model)
                    logger.info("Cross-Encoder 重排模型预热完成")
        except Exception:
            logger.warning("RAG 预热失败，首次请求可能较慢")
    asyncio.create_task(_warm_chromadb())

    yield
    if proactive_task:
        proactive_task.cancel()
    # Flush Langfuse events before shutdown
    flush_langfuse()
    from app.core.concurrency import shutdown_concurrency
    shutdown_concurrency()
    from app.services.context_manager import close_redis
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

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
    """Liveness probe — 进程是否存活，不探测依赖。"""
    return {"status": "ok", "version": settings.APP_VERSION}


@app.get("/health/ready")
async def health_ready():
    """Readiness probe — 探测 DB / Redis 是否可用。"""
    checks: dict[str, dict] = {}
    overall_ok = True

    # DB
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            result.scalar_one()
        checks["database"] = {"status": "ok"}
    except Exception as e:
        overall_ok = False
        checks["database"] = {"status": "error", "error": str(e)[:200]}

    # Redis
    try:
        import redis.asyncio as redis_asyncio
        client = redis_asyncio.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        try:
            pong = await client.ping()
            checks["redis"] = {"status": "ok" if pong else "error"}
            if not pong:
                overall_ok = False
        finally:
            await client.aclose()
    except Exception as e:
        overall_ok = False
        checks["redis"] = {"status": "error", "error": str(e)[:200]}

    payload = {
        "status": "ok" if overall_ok else "degraded",
        "version": settings.APP_VERSION,
        "checks": checks,
    }
    return payload if overall_ok else (payload, 503)
