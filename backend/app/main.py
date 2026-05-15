from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.privacy import router as privacy_router
from app.api.projects import router as projects_router
from app.api.reports import router as reports_router
from app.db.database import init_db

app = FastAPI(title="HEZ Tool API", version="0.1.0")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(projects_router, prefix="/api/projects", tags=["projects"])
app.include_router(reports_router, prefix="/api/reports", tags=["reports"])
app.include_router(privacy_router, prefix="/api/privacy", tags=["privacy"])
