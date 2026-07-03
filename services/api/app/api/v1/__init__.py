from fastapi import APIRouter
from app.api.v1 import (
    auth,
    consultations,
    eval as eval_routes,
    handoffs,
    health_events,
    iot,
    knowledge_graph,
    memory,
    mcp_servers,
    plugins,
    privacy,
    proactive,
    rag,
    registration,
    records,
    reminders,
    scheduled_tasks,
    skills,
    upload,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(consultations.router)
api_router.include_router(health_events.router)
api_router.include_router(reminders.router)
api_router.include_router(records.router)
api_router.include_router(skills.router)
api_router.include_router(upload.router)
api_router.include_router(registration.router)
api_router.include_router(iot.router)
api_router.include_router(rag.router)
api_router.include_router(eval_routes.router)
api_router.include_router(handoffs.router)
api_router.include_router(plugins.router)
api_router.include_router(proactive.router)
api_router.include_router(privacy.router)
api_router.include_router(memory.router)
api_router.include_router(mcp_servers.router)
api_router.include_router(knowledge_graph.router)
api_router.include_router(scheduled_tasks.router)
