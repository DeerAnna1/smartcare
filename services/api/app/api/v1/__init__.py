from fastapi import APIRouter
from app.api.v1 import auth, consultations, health_events, reminders, records, skills, upload, registration

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(consultations.router)
api_router.include_router(health_events.router)
api_router.include_router(reminders.router)
api_router.include_router(records.router)
api_router.include_router(skills.router)
api_router.include_router(upload.router)
api_router.include_router(registration.router)
