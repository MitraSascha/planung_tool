"""Analytics-API: KPIs aus den Berichten/Problemen/Stunden."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.orm_models import (
    MaterialItem,
    MaterialUsage,
    Project,
    ProjectSection,
    User,
)
from app.models.analytics import (
    AtRiskProjectRead,
    HoursPerSectionRead,
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
        hours_total_planned=pa.hours_total_planned,
        hours_total_delta=pa.hours_total_delta,
        hours_total_percent=pa.hours_total_percent,
        hours_total_status=pa.hours_total_status,
        hours_by_user=[HoursPerUserRead(**h.__dict__) for h in pa.hours_by_user],
        hours_by_section=[HoursPerSectionRead(**h.__dict__) for h in pa.hours_by_section],
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


# ───────────────────────────────────────────────────────────────────────────
# Material-Analytics: was wurde verbaut, was fehlt noch
# ───────────────────────────────────────────────────────────────────────────
class MaterialPerItem(BaseModel):
    item_id: int
    name: str
    kind: str
    section_number: int | None
    section_name: str | None
    soll_qty: float | None
    ist_qty: float | None
    remaining: float | None
    percent_done: float | None  # 0..100, None wenn kein soll
    status: str
    unit: str | None
    usage_count: int
    last_used_at: date | None


class MaterialPerSection(BaseModel):
    section_number: int | None
    section_name: str | None
    items_total: int
    items_completed: int  # ist >= soll
    total_soll: float
    total_ist: float
    percent_done: float | None


class MaterialWeeklyPoint(BaseModel):
    week_start: date
    total_qty_used: float
    usage_count: int


class MaterialTopItem(BaseModel):
    item_id: int | None
    name: str
    total_used: float
    unit: str | None


class MaterialAnalyticsRead(BaseModel):
    project_slug: str
    items_total: int
    items_completed: int
    items_overrun: int  # ist > soll (mehr verbaut als geplant)
    total_soll: float
    total_ist: float
    percent_done: float | None
    usage_count: int
    per_item: list[MaterialPerItem]
    per_section: list[MaterialPerSection]
    weekly_burndown: list[MaterialWeeklyPoint]
    top_items: list[MaterialTopItem]


@router.get(
    "/projects/{slug}/material-analytics",
    response_model=MaterialAnalyticsRead,
)
def get_material_analytics(
    slug: str,
    weeks_back: int = 8,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MaterialAnalyticsRead:
    project = db.query(Project).filter(Project.slug == slug).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    weeks_back = max(1, min(weeks_back, 52))

    items = (
        db.query(MaterialItem)
        .filter(MaterialItem.project_id == project.id)
        .order_by(MaterialItem.section_number, MaterialItem.kind, MaterialItem.name)
        .all()
    )
    sections = {
        s.number: s.name
        for s in db.query(ProjectSection)
        .filter(ProjectSection.project_id == project.id)
        .all()
    }

    # Usage-Stats pro Item (count + last_used_at)
    usage_stats = {
        row[0]: (row[1], row[2])
        for row in db.query(
            MaterialUsage.material_item_id,
            func.count(MaterialUsage.id),
            func.max(MaterialUsage.used_at),
        )
        .filter(MaterialUsage.project_id == project.id)
        .group_by(MaterialUsage.material_item_id)
        .all()
    }

    per_item: list[MaterialPerItem] = []
    for it in items:
        soll = it.soll_qty
        ist = it.ist_qty
        remaining = (soll - (ist or 0)) if soll is not None else None
        percent = ((ist or 0) / soll * 100.0) if soll else None
        count, last_used = usage_stats.get(it.id, (0, None))
        per_item.append(
            MaterialPerItem(
                item_id=it.id,
                name=it.name,
                kind=it.kind,
                section_number=it.section_number,
                section_name=sections.get(it.section_number) if it.section_number else None,
                soll_qty=soll,
                ist_qty=ist,
                remaining=remaining,
                percent_done=round(percent, 1) if percent is not None else None,
                status=it.status,
                unit=it.unit,
                usage_count=count,
                last_used_at=last_used,
            )
        )

    # Aggregation pro Abschnitt
    sec_buckets: dict[int | None, dict] = defaultdict(
        lambda: {"items_total": 0, "items_completed": 0, "total_soll": 0.0, "total_ist": 0.0}
    )
    for pi in per_item:
        b = sec_buckets[pi.section_number]
        b["items_total"] += 1
        if pi.soll_qty is not None and pi.ist_qty is not None and pi.ist_qty >= pi.soll_qty:
            b["items_completed"] += 1
        b["total_soll"] += pi.soll_qty or 0.0
        b["total_ist"] += pi.ist_qty or 0.0

    per_section = [
        MaterialPerSection(
            section_number=sn,
            section_name=sections.get(sn) if sn else None,
            items_total=b["items_total"],
            items_completed=b["items_completed"],
            total_soll=b["total_soll"],
            total_ist=b["total_ist"],
            percent_done=round(b["total_ist"] / b["total_soll"] * 100.0, 1)
            if b["total_soll"]
            else None,
        )
        for sn, b in sorted(
            sec_buckets.items(), key=lambda kv: (kv[0] is None, kv[0] or 0)
        )
    ]

    # Wochen-Burndown
    today = date.today()
    cutoff = today - timedelta(days=7 * weeks_back)
    weekly_buckets: dict[date, dict] = defaultdict(lambda: {"qty": 0.0, "count": 0})
    for u in (
        db.query(MaterialUsage)
        .filter(
            MaterialUsage.project_id == project.id,
            MaterialUsage.used_at >= cutoff,
        )
        .all()
    ):
        monday = u.used_at - timedelta(days=u.used_at.weekday())
        weekly_buckets[monday]["qty"] += u.qty_used
        weekly_buckets[monday]["count"] += 1

    weekly_burndown = [
        MaterialWeeklyPoint(
            week_start=wk, total_qty_used=b["qty"], usage_count=b["count"]
        )
        for wk, b in sorted(weekly_buckets.items())
    ]

    # Top-Items nach verbauter Menge (Top 10)
    top_items = sorted(
        per_item, key=lambda x: (x.ist_qty or 0.0), reverse=True
    )[:10]
    top_items_out = [
        MaterialTopItem(
            item_id=pi.item_id,
            name=pi.name,
            total_used=pi.ist_qty or 0.0,
            unit=pi.unit,
        )
        for pi in top_items
        if (pi.ist_qty or 0.0) > 0
    ]

    items_completed = sum(
        1 for pi in per_item if pi.soll_qty is not None and pi.ist_qty is not None and pi.ist_qty >= pi.soll_qty
    )
    items_overrun = sum(
        1 for pi in per_item if pi.soll_qty is not None and pi.ist_qty is not None and pi.ist_qty > pi.soll_qty
    )
    total_soll = sum((pi.soll_qty or 0.0) for pi in per_item)
    total_ist = sum((pi.ist_qty or 0.0) for pi in per_item)
    usage_count_total = sum(pi.usage_count for pi in per_item)

    return MaterialAnalyticsRead(
        project_slug=slug,
        items_total=len(per_item),
        items_completed=items_completed,
        items_overrun=items_overrun,
        total_soll=total_soll,
        total_ist=total_ist,
        percent_done=round(total_ist / total_soll * 100.0, 1) if total_soll else None,
        usage_count=usage_count_total,
        per_item=per_item,
        per_section=per_section,
        weekly_burndown=weekly_burndown,
        top_items=top_items_out,
    )
