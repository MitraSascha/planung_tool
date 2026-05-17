"""Analytics-API: KPIs aus den Berichten/Problemen/Stunden."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.orm_models import Project, User
from app.models.analytics import (
    AtRiskProjectRead,
    HoursPerUserRead,
    PortfolioAnalyticsRead,
    ProjectAnalyticsRead,
    StatusBreakdownRead,
    TimeSeriesPointRead,
    TopItemRead,
)
from app.services.analytics import portfolio_analytics, project_analytics
from app.services.auth import (
    ADMIN_ROLES,
    PROJECT_READ_ROLES,
    SITE_LEAD_ROLES,
    get_current_user,
    require_global_role,
    require_project_role,
)

router = APIRouter()


def _to_pa_read(pa) -> ProjectAnalyticsRead:
    return ProjectAnalyticsRead(
        project_slug=pa.project_slug,
        project_name=pa.project_name,
        period_start=pa.period_start,
        period_end=pa.period_end,
        daily_status=StatusBreakdownRead(**pa.daily_status.__dict__),
        weekly_status=StatusBreakdownRead(**pa.weekly_status.__dict__),
        blockers_open=pa.blockers_open,
        blockers_total=pa.blockers_total,
        blockers_by_severity=pa.blockers_by_severity,
        material_open=pa.material_open,
        material_total=pa.material_total,
        risks_open=pa.risks_open,
        risks_total=pa.risks_total,
        materials_by_status=pa.materials_by_status,
        hours_total_soll=pa.hours_total_soll,
        hours_total_ist=pa.hours_total_ist,
        hours_by_user=[HoursPerUserRead(**h.__dict__) for h in pa.hours_by_user],
        daily_status_series=[TimeSeriesPointRead(**p.__dict__) for p in pa.daily_status_series],
        blockers_opened_per_day=[TimeSeriesPointRead(**p.__dict__) for p in pa.blockers_opened_per_day],
        offer_total_net=pa.offer_total_net,
        offer_count=pa.offer_count,
        top_blockers=[TopItemRead(**t.__dict__) for t in pa.top_blockers],
        top_material_issues=[TopItemRead(**t.__dict__) for t in pa.top_material_issues],
    )


@router.get(
    "/projects/{slug}/analytics",
    response_model=ProjectAnalyticsRead,
)
def get_project_analytics(
    slug: str,
    weeks_back: int = 4,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectAnalyticsRead:
    project = db.query(Project).filter(Project.slug == slug).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    pa = project_analytics(db, project, weeks_back=max(1, min(weeks_back, 52)))
    return _to_pa_read(pa)


@router.get(
    "/portfolio",
    response_model=PortfolioAnalyticsRead,
)
def get_portfolio_analytics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortfolioAnalyticsRead:
    """Cross-Projekt-Sicht für Projekt-/Bauleitung. Admin + SITE_LEAD only."""
    require_global_role(current_user, SITE_LEAD_ROLES)
    pf = portfolio_analytics(db)
    return PortfolioAnalyticsRead(
        generated_at=pf.generated_at,
        project_count=pf.project_count,
        active_project_count=pf.active_project_count,
        projects_at_risk=[AtRiskProjectRead(**p) for p in pf.projects_at_risk],
        total_hours_ist_last_7d=pf.total_hours_ist_last_7d,
        total_hours_soll_last_7d=pf.total_hours_soll_last_7d,
        open_blockers_total=pf.open_blockers_total,
        open_material_total=pf.open_material_total,
        open_risks_total=pf.open_risks_total,
        total_offer_value_net=pf.total_offer_value_net,
    )
