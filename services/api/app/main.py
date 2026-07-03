from contextlib import asynccontextmanager
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
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
from app.jobs.scheduled_task_runner import scheduled_task_loop
from app.core.observability import init_langfuse, flush_langfuse

configure_logging()
init_sentry()

logger = logging.getLogger(__name__)
settings = get_settings()


# ─── 版本标识 ────────────────────────────────────────────────────────────────
VERSION_PROMPT = "v2.1"
VERSION_AGENT_GRAPH = "v2.0-multi-agent"
VERSION_TOOL_SCHEMA = "v1.0"
VERSION_EMBEDDING_MODEL = "v1.0"


def _validate_production_config():
    """生产环境配置校验：缺少必要配置时直接拒绝启动。"""
    if settings.ENV != "production":
        return

    errors = []
    if settings.AUTH_SECRET in ("dev-auth-secret-change-me", ""):
        errors.append("AUTH_SECRET 使用默认值，生产环境必须修改")
    if settings.WEBHOOK_SECRET in ("dev-webhook-secret-change-me", ""):
        errors.append("WEBHOOK_SECRET 使用默认值，生产环境必须修改")
    if settings.IOT_WEBHOOK_HMAC_SECRET in ("dev-iot-hmac-secret-change-me", ""):
        errors.append("IOT_WEBHOOK_HMAC_SECRET 使用默认值，生产环境必须修改")
    if not settings.OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY 未配置")
    if "localhost" in settings.DATABASE_URL:
        errors.append("DATABASE_URL 指向 localhost，生产环境应使用远程数据库")
    if "localhost" in settings.REDIS_URL:
        errors.append("REDIS_URL 指向 localhost，生产环境应使用远程 Redis")

    if errors:
        for err in errors:
            logger.error(f"[CONFIG ERROR] {err}")
        raise RuntimeError(f"生产配置校验失败，共 {len(errors)} 项错误。请修复后重启。")


def _emit_capability_report():
    """启动时输出不含密钥的能力报告。"""
    # 检测 RAG collection 是否可用
    rag_status = "unknown"
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
        chroma_dir = os.path.join(os.path.dirname(__file__), "..", "data", "chroma_db")
        if os.path.isdir(chroma_dir):
            client = chromadb.PersistentClient(path=chroma_dir, settings=ChromaSettings(anonymized_telemetry=False))
            collections = [c.name for c in client.list_collections()]
            rag_status = f"available (collections: {collections})"
        else:
            rag_status = "no_chroma_dir"
    except Exception as e:
        rag_status = f"error: {str(e)[:100]}"

    # 检测 embedding 模型
    embedding_status = "unknown"
    try:
        from sentence_transformers import SentenceTransformer
        # 只检查路径是否可访问，不实际加载
        embedding_status = f"configured ({settings.RAG_EMBEDDING_MODEL})"
    except ImportError:
        embedding_status = "sentence_transformers not installed"

    report = {
        "app_version": settings.APP_VERSION,
        "env": settings.ENV,
        "llm_model": settings.LLM_MODEL,
        "llm_base_url": settings.OPENAI_BASE_URL.split("//")[0] + "//" + "***",
        "vision_support": "mimo-v2-omni" in settings.LLM_MODEL or "omni" in settings.LLM_MODEL.lower(),
        "asr_model": settings.WHISPER_MODEL,
        "rag_embedding_model": settings.RAG_EMBEDDING_MODEL,
        "rag_reranker_enabled": settings.RAG_RERANKER_ENABLED,
        "rag_collection_status": rag_status,
        "langfuse_enabled": settings.LANGFUSE_ENABLED,
        "proactive_job_enabled": settings.PROACTIVE_JOB_ENABLED,
        "concurrency_enabled": settings.CONCURRENCY_ENABLED,
        "versions": {
            "prompt": VERSION_PROMPT,
            "agent_graph": VERSION_AGENT_GRAPH,
            "tool_schema": VERSION_TOOL_SCHEMA,
            "embedding_model": VERSION_EMBEDDING_MODEL,
        },
    }
    logger.info(f"[CAPABILITY REPORT] {report}")
    return report


def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "请求过于频繁，请稍后再试", "retry_after": exc.detail},
    )


DEFAULT_SKILLS = [
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


async def _recover_stale_generation_runs() -> int:
    """Expire generation leases abandoned by a crashed worker."""
    from sqlalchemy import select
    from app.models.models import ConsultationSession, ConversationMessage

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=120)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ConsultationSession).where(
                ConsultationSession.active_run_id.is_not(None),
                ConsultationSession.active_run_heartbeat_at < cutoff,
            )
        )
        sessions = list(result.scalars())
        message_filters = [
            ConversationMessage.role == "assistant",
            ConversationMessage.status.in_(["pending", "streaming"]),
            ConversationMessage.created_at < cutoff,
        ]
        # Also catches a worker crash before it acquired the session lease.
        rows = await db.execute(select(ConversationMessage).where(*message_filters))
        stale_messages = list(rows.scalars())
        for message in stale_messages:
            message.status = "failed"
            message.content_json = '{"content":"生成进程已重启，请重试本条消息","error":"generation_lease_expired"}'
            message.completed_at = datetime.now(timezone.utc)
        for item in sessions:
            item.active_run_id = None
            item.active_run_heartbeat_at = None
        await db.commit()
        recovered = len(sessions) + len(stale_messages)
        if recovered:
            logger.warning(
                "已恢复过期问诊生成：%s 个租约，%s 条消息",
                len(sessions), len(stale_messages),
            )
        return recovered


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 生产配置校验（失败直接拒绝启动）
    _validate_production_config()

    # 启动能力报告
    capability_report = _emit_capability_report()
    app.state.capability_report = capability_report

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

    # 定时科普任务调度器
    scheduled_task_bg = asyncio.create_task(scheduled_task_loop())

    async def generation_lease_sweeper():
        while True:
            try:
                await _recover_stale_generation_runs()
            except Exception:
                logger.exception("问诊生成租约恢复失败")
            await asyncio.sleep(30)

    generation_lease_task = asyncio.create_task(generation_lease_sweeper())

    # 种植默认技能包（确保药物相互作用和挂号预约始终可用）
    await _seed_default_skills()
    try:
        from app.services.extension_registry import sync_extension_registry
        async with AsyncSessionLocal() as db:
            await sync_extension_registry(db)
            await db.commit()
        logger.info("Skill / Tool 注册表同步完成")
    except Exception:
        logger.exception("Skill / Tool 注册表同步失败")

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
    scheduled_task_bg.cancel()
    generation_lease_task.cancel()
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
    """Readiness probe — 探测 DB / Redis / RAG / 模型 是否可用。"""
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

    # RAG / ChromaDB
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
        chroma_dir = os.path.join(os.path.dirname(__file__), "..", "data", "chroma_db")
        if os.path.isdir(chroma_dir):
            client = chromadb.PersistentClient(path=chroma_dir, settings=ChromaSettings(anonymized_telemetry=False))
            collections = [c.name for c in client.list_collections()]
            checks["rag"] = {"status": "ok", "collections": collections}
        else:
            checks["rag"] = {"status": "no_chroma_dir"}
    except Exception as e:
        checks["rag"] = {"status": "error", "error": str(e)[:200]}

    # LLM 连通性（只检查配置，不发真实请求）
    checks["llm"] = {
        "status": "configured" if settings.OPENAI_API_KEY else "missing_api_key",
        "model": settings.LLM_MODEL,
    }

    payload = {
        "status": "ok" if overall_ok else "degraded",
        "version": settings.APP_VERSION,
        "checks": checks,
    }
    return payload if overall_ok else (payload, 503)


@app.get("/capability")
async def capability():
    """返回当前系统能力报告（受保护端点，不含密钥）。"""
    return getattr(app.state, "capability_report", {})
