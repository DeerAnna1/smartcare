# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SmartCare / ZhiYu — a Chinese-language full-stack health AI assistant platform with a "dual workspace" architecture:
- **Consultation Workspace**: LLM-powered multi-turn health consultations via a LangGraph state machine. Collects symptoms, performs triage, generates structured HealthEvent cards.
- **Execution Workspace**: Drives downstream actions from HealthEvent cards — medication reminders, health records (EHR), hospital appointment booking, IoT vital monitoring.

## Repository Structure

This is a multi-project repo (not a monorepo). Each component has its own package manager:

```
apps/web/                    → Next.js 16 frontend (npm)
services/api/                → FastAPI backend (pip/venv)
infra/docker/                → Docker Compose orchestration
stitch_healthloop_agent/     → Design reference / prototype HTML screens
```

## Common Commands

### Start all services (Docker)
```bash
docker compose -f infra/docker/docker-compose.yml up -d --build
```
Services: postgres (5433), redis (6380), api (8001), web (3001).

### Frontend (apps/web/)
```bash
cd apps/web
npm run dev        # Dev server (default port 3000, Docker uses 3001)
npm run build      # Production build (standalone output)
npm run lint       # ESLint
```

### Backend (services/api/)
```bash
cd services/api
# Activate venv first, then:
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload   # Dev server
alembic upgrade head                                         # Run migrations
alembic revision --autogenerate -m "description"             # Create migration
```

Seed registration data (hospitals, departments, schedules):
```bash
docker exec med_api python3 /app/scripts/seed_registration.py
```

### Environment Setup
```bash
cd infra/docker
cp .env.example .env   # Then fill in OPENAI_API_KEY, etc.
```

## Architecture

### Frontend → Backend Communication
All data flows through a REST API client at `apps/web/src/lib/api-client.ts`. Base URL from `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). All endpoints under `/api/v1/*`. Auth via Bearer token stored in localStorage + cookie.

The chat interface is **non-streaming** — `sendMessage` returns a full response, and the page polls every 2.5s via `setInterval`.

### Backend Structure (services/api/app/)
```
main.py                    → FastAPI app, lifespan, CORS, /health endpoint
core/config.py             → All settings via pydantic-settings (env-based)
core/database.py           → Async SQLAlchemy engine + session factory
api/v1/                    → Route modules (auth, consultations, health_events,
                            records, reminders, skills, upload, registration,
                            iot, plugins, proactive, handoffs)
api/deps/auth.py           → get_current_user / get_current_user_required deps
models/models.py           → 17 SQLAlchemy models (all in one file)
services/                  → Business logic (auth, consultation orchestrator,
                            registration, risk_guardrail, proactive_intervention)
orchestrators/             → LangGraph state machine for consultation flow
```

### Key Backend Patterns
- **Auth**: Custom hand-rolled JWT (HS256, PBKDF2 password hashing). No third-party auth library.
- **Database**: SQLAlchemy 2.0 async with `asyncpg`. Auto-creates tables in dev mode; use Alembic for production.
- **LLM**: OpenAI-compatible API via `OPENAI_BASE_URL` + LangGraph for multi-step orchestration.
- **Skill invocation**: LLM outputs `` ```invoke `` code blocks → backend parses and dispatches to skill executors.
- **IoT webhooks**: HMAC-SHA256 signature verification with timestamp-based replay protection.
- **Risk guardrails**: Pattern-based keyword detection in user input and IoT data triggers human handoff tickets.

### Frontend Structure (apps/web/src/)
```
app/
  (consultation)/          → Chat, conclusion, event-confirm routes
  (execution)/             → Tasks, health-records, records, iot-simulator routes
  (skills)/                → Skill management routes
  auth/                    → Login/register page
components/
  layout/                  → TopNavBar, SideNavBar
  auth/                    → AuthClientPage
  input/                   → AvatarUpload, FileUpload, VoiceToText
lib/
  api-client.ts            → Centralized fetch wrapper for all API calls
  auth.ts                  → Token management (localStorage + cookie)
```

Route groups `(consultation)`, `(execution)`, `(skills)` each have their own `layout.tsx` with shared nav shell. Parentheses keep them out of the URL path.

### Styling
Tailwind CSS v4 with Material Design 3 theme tokens defined in `globals.css`. All styling via Tailwind utility classes. Icons via Google Material Symbols Outlined. Fonts: Inter (body), Manrope (headlines).

### Middleware
`apps/web/middleware.ts` protects routes by checking the `medhelp_token` cookie. Unauthenticated users redirect to `/auth?redirect=...`.

## Key Configuration Files

| File | Purpose |
|------|---------|
| `infra/docker/.env.example` | Env var template (OPENAI_API_KEY, OPENAI_BASE_URL, etc.) |
| `services/api/app/core/config.py` | All backend settings with defaults |
| `services/api/alembic.ini` | Alembic migration config |
| `apps/web/.env.local` | Frontend env (NEXT_PUBLIC_API_URL) |
| `apps/web/next.config.ts` | Next.js config (standalone output) |

## Deployment

Production on Railway. Dockerfiles in `apps/web/Dockerfile` (Node 20 Alpine, standalone build) and `services/api/Dockerfile` (Python 3.11-slim). Frontend defaults `NEXT_PUBLIC_API_URL` to `http://localhost:8001` at build time.

## Notes

- No test framework is configured for either frontend or backend.
- The Prisma/SQLite setup in `apps/web/prisma/` is a legacy artifact — all data goes through the FastAPI backend now.
- The `llm.ts` server-side file in the frontend is kept as backup; actual LLM calls go through the backend.
- UI language is Chinese (zh-CN).
