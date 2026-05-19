"""HERO-Integration: Admin-Endpoints für Partner-Mapping + Status.

Endpoints:
  * ``GET  /api/hero/status``           — ist die Integration konfiguriert?
  * ``GET  /api/hero/partners``         — Mitarbeiter aus HERO (für UI-Dropdowns)
  * ``POST /api/hero/sync-partners``    — Auto-Mapping User ↔ HERO-Partner per
                                          normalisiertem Namen
  * ``GET  /api/hero/search-projects``  — globale Projekt-Suche (für Project-Mapping)
  * ``GET  /api/hero/tracking-categories`` — Liste der TT-Kategorien

Nur ADMIN-Rolle.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.orm_models import Project, User
from app.services.auth import ADMIN_ROLES, get_current_user, require_global_role
from app.services.hero.client import HeroError, is_configured
from app.services.hero.service import (
    get_company_partners,
    get_tracking_time_categories,
    search_project_matches,
    sync_partners_to_users,
)
from app.services.hero.tracking_push import dry_run_daily_report

logger = logging.getLogger(__name__)
router = APIRouter()


class HeroStatusRead(BaseModel):
    configured: bool
    graphql_url: str | None = None


class HeroPartnerRead(BaseModel):
    id: int
    full_name: str
    email: str | None = None


class PartnerSyncResult(BaseModel):
    matched: int
    ambiguous: int
    unchanged: int
    no_match: int


@router.get("/status", response_model=HeroStatusRead)
def hero_status(current_user: User = Depends(get_current_user)) -> HeroStatusRead:
    from app.core.settings import settings as _settings
    return HeroStatusRead(
        configured=is_configured(),
        graphql_url=_settings.hero_graphql_url if is_configured() else None,
    )


@router.get("/partners", response_model=list[HeroPartnerRead])
def list_hero_partners(
    current_user: User = Depends(get_current_user),
) -> list[HeroPartnerRead]:
    """Live-Liste der HERO-Mitarbeiter. Lead-Rollen brauchen das für UI-Pickers
    (z.B. Admin-Panel, wo manuell ein User auf einen Partner gemappt wird)."""
    require_global_role(current_user, ADMIN_ROLES)
    if not is_configured():
        raise HTTPException(status_code=503, detail="HERO_API_TOKEN nicht konfiguriert")
    try:
        rows = get_company_partners()
    except HeroError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [HeroPartnerRead(**r) for r in rows]


@router.post("/sync-partners", response_model=PartnerSyncResult)
def sync_partners(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PartnerSyncResult:
    """Auto-Mapping: alle User mit leerem ``hero_partner_id`` werden per
    normalisiertem ``display_name`` mit HERO-Partnern gematcht."""
    require_global_role(current_user, ADMIN_ROLES)
    if not is_configured():
        raise HTTPException(status_code=503, detail="HERO_API_TOKEN nicht konfiguriert")
    try:
        counters = sync_partners_to_users(db)
    except HeroError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return PartnerSyncResult(**counters)


@router.get("/search-projects")
def search_projects(
    q: str = Query(..., min_length=2),
    first: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    require_global_role(current_user, ADMIN_ROLES)
    if not is_configured():
        raise HTTPException(status_code=503, detail="HERO_API_TOKEN nicht konfiguriert")
    try:
        return search_project_matches(q, first=first)
    except HeroError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/tracking-categories")
def tracking_categories(
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    require_global_role(current_user, ADMIN_ROLES)
    if not is_configured():
        raise HTTPException(status_code=503, detail="HERO_API_TOKEN nicht konfiguriert")
    try:
        return get_tracking_time_categories()
    except HeroError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


class ProjectMappingUpdate(BaseModel):
    hero_project_match_id: int | None


@router.patch("/projects/{slug}/mapping", response_model=dict)
def update_project_mapping(
    slug: str,
    payload: ProjectMappingUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Admin: setzt ``hero_project_match_id`` für ein Projekt.

    NULL setzt das Mapping zurück (Push erfolgt dann ohne Projekt-Bezug)."""
    require_global_role(current_user, ADMIN_ROLES)
    project = db.query(Project).filter(Project.slug == slug).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    project.hero_project_match_id = payload.hero_project_match_id
    db.commit()
    return {
        "slug": project.slug,
        "hero_project_match_id": project.hero_project_match_id,
    }


@router.get("/dry-run/daily-reports/{report_id}")
def dry_run_push(
    report_id: int,
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Zeigt was beim HERO-Push für diesen Tagesbericht gesendet würde —
    ohne den Call tatsächlich auszuführen. Admin-Diagnose."""
    require_global_role(current_user, ADMIN_ROLES)
    if not is_configured():
        raise HTTPException(status_code=503, detail="HERO_API_TOKEN nicht konfiguriert")
    return dry_run_daily_report(report_id)
