from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.analytics import router as analytics_router
from app.api.articles import router as articles_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.domains import router as domains_router
from app.api.dsgvo import router as dsgvo_router
from app.api.form_responses import router as form_responses_router
from app.api.heating import router as heating_router
from app.api.media import router as media_router
from app.api.nachkalkulation import router as nachkalkulation_router
from app.api.offers import router as offers_router
from app.api.privacy import router as privacy_router
from app.api.projects import router as projects_router
from app.api.push import router as push_router
from app.api.reports import router as reports_router
from app.api.templates import router as templates_router
from app.api.voice import router as voice_router
from app.db.database import init_db
from app.services.audit_log import (
    AuditContextMiddleware,
    register_listeners as register_audit_listeners,
)
from app.services.auto_sync import register_listeners as register_auto_sync_listeners
from app.services.push_hooks import register_listeners as register_push_listeners
from app.services.whisper_pipeline import register_listeners as register_whisper_listeners

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    register_whisper_listeners()
    register_push_listeners()
    register_audit_listeners()
    register_auto_sync_listeners()
    yield


app = FastAPI(title="HEZ Tool API", version="0.1.0", lifespan=lifespan)

if AuditContextMiddleware is not None:
    app.add_middleware(AuditContextMiddleware)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(projects_router, prefix="/api/projects", tags=["projects"])
app.include_router(form_responses_router, prefix="/api/projects", tags=["form-responses"])
app.include_router(reports_router, prefix="/api/reports", tags=["reports"])
app.include_router(privacy_router, prefix="/api/privacy", tags=["privacy"])
app.include_router(heating_router, prefix="/api", tags=["heating"])
app.include_router(offers_router, prefix="/api", tags=["offers"])
app.include_router(analytics_router, prefix="/api/analytics", tags=["analytics"])
app.include_router(media_router, prefix="/api", tags=["media"])
app.include_router(push_router, prefix="/api/push", tags=["push"])
app.include_router(audit_router, prefix="/api/audit", tags=["audit"])
app.include_router(dsgvo_router, prefix="/api/dsgvo", tags=["dsgvo"])
app.include_router(articles_router, prefix="/api", tags=["articles"])
app.include_router(templates_router, prefix="/api/templates", tags=["templates"])
app.include_router(domains_router, prefix="/api/projects", tags=["domains"])
app.include_router(nachkalkulation_router, prefix="/api/projects", tags=["nachkalkulation"])
app.include_router(voice_router, prefix="/api/voice", tags=["voice"])
