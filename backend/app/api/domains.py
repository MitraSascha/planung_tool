"""CRUD endpoints for the five domain entities the new templates depend on:

- section_schedules  (one row per ProjectSection, overrides derived termin)
- team_status        (one row per project × user × day)
- material_items     (extendable inventory per project, optionally per section)
- risk_issues        (risks and defects per project, extendable list)
- blockers           (extendable blocker list — table existed already)

Routes live under /api/projects/{slug}/<domain>. Read is gated to
PROJECT_READ_ROLES, write to SITE_LEAD_ROLES.
"""
from __future__ import annotations

from datetime import date as _date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.orm_models import (
    Blocker,
    DailyReport,
    MaterialItem,
    MaterialUsage,
    Project,
    ProjectSection,
    RiskIssue,
    SectionSchedule,
    TeamStatusEntry,
    User,
)
from app.services.auth import (
    PROJECT_READ_ROLES,
    SITE_LEAD_ROLES,
    get_current_user,
    require_project_role,
)
from app.services import template_publisher
from app.services.material_usage import recalc_ist_qty


router = APIRouter()


def _load_project(db: Session, slug: str) -> Project:
    project = db.query(Project).filter(Project.slug == slug).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _republish_sheets(db: Session, slug: str) -> None:
    """Re-render alle HTML-Sheets nach einer mutierenden Operation.
    Sonst sieht der User den alten statischen Stand bei Page-Reload.
    Best-effort: Render-Fehler dürfen die Haupt-Operation nicht
    zum Scheitern bringen.
    """
    try:
        template_publisher.publish_templates_to_storage(db, slug)
    except Exception:
        pass


# ───────────────────────────────────────────────────────────────────────────
# section_schedules
# ───────────────────────────────────────────────────────────────────────────
class SectionScheduleIn(BaseModel):
    section_id: int
    start_date: _date | None = None
    end_date: _date | None = None
    notes: str | None = None


class SectionScheduleOut(SectionScheduleIn):
    id: int


@router.get("/{slug}/section-schedules", response_model=list[SectionScheduleOut])
def list_section_schedules(slug: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    rows = (
        db.query(SectionSchedule)
        .join(ProjectSection, SectionSchedule.section_id == ProjectSection.id)
        .filter(ProjectSection.project_id == project.id)
        .all()
    )
    return [SectionScheduleOut(id=r.id, section_id=r.section_id, start_date=r.start_date, end_date=r.end_date, notes=r.notes) for r in rows]


@router.put("/{slug}/section-schedules", response_model=SectionScheduleOut)
def upsert_section_schedule(slug: str, payload: SectionScheduleIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    section = db.query(ProjectSection).filter(ProjectSection.id == payload.section_id, ProjectSection.project_id == project.id).first()
    if section is None:
        raise HTTPException(status_code=404, detail="Section not part of this project")
    row = db.query(SectionSchedule).filter(SectionSchedule.section_id == payload.section_id).first()
    if row is None:
        row = SectionSchedule(section_id=payload.section_id)
        db.add(row)
    row.start_date = payload.start_date
    row.end_date = payload.end_date
    row.notes = payload.notes
    db.commit()
    db.refresh(row)
    # Meilensteine aktualisieren — neues planned_date fließt durch.
    from app.services.milestones import sync_milestones
    try:
        sync_milestones(db, project.id)
    except Exception:
        db.rollback()
    return SectionScheduleOut(id=row.id, section_id=row.section_id, start_date=row.start_date, end_date=row.end_date, notes=row.notes)


# ───────────────────────────────────────────────────────────────────────────
# team_status
# ───────────────────────────────────────────────────────────────────────────
class TeamStatusIn(BaseModel):
    user_id: int
    day: _date
    status: str = "green"
    soll_hours: float | None = None
    ist_hours: float | None = None
    note: str | None = None


class TeamStatusOut(TeamStatusIn):
    id: int
    display_name: str | None = None


@router.get("/{slug}/team-status", response_model=list[TeamStatusOut])
def list_team_status(slug: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    rows = (
        db.query(TeamStatusEntry, User)
        .join(User, TeamStatusEntry.user_id == User.id)
        .filter(TeamStatusEntry.project_id == project.id)
        .order_by(TeamStatusEntry.day.desc(), User.display_name)
        .all()
    )
    return [
        TeamStatusOut(id=t.id, user_id=t.user_id, day=t.day, status=t.status, soll_hours=t.soll_hours, ist_hours=t.ist_hours, note=t.note, display_name=u.display_name)
        for t, u in rows
    ]


@router.post("/{slug}/team-status", response_model=TeamStatusOut)
def create_team_status(slug: str, payload: TeamStatusIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    row = (
        db.query(TeamStatusEntry)
        .filter(
            TeamStatusEntry.project_id == project.id,
            TeamStatusEntry.user_id == payload.user_id,
            TeamStatusEntry.day == payload.day,
        )
        .first()
    )
    if row is None:
        row = TeamStatusEntry(project_id=project.id, user_id=payload.user_id, day=payload.day)
        db.add(row)
    row.status = payload.status
    row.soll_hours = payload.soll_hours
    row.ist_hours = payload.ist_hours
    row.note = payload.note
    db.commit()
    db.refresh(row)
    user = db.query(User).filter(User.id == row.user_id).first()
    return TeamStatusOut(id=row.id, user_id=row.user_id, day=row.day, status=row.status, soll_hours=row.soll_hours, ist_hours=row.ist_hours, note=row.note, display_name=user.display_name if user else None)


@router.delete("/{slug}/team-status/{entry_id}")
def delete_team_status(slug: str, entry_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    row = db.query(TeamStatusEntry).filter(TeamStatusEntry.id == entry_id, TeamStatusEntry.project_id == project.id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    db.delete(row)
    db.commit()
    return {"deleted": entry_id}


# ───────────────────────────────────────────────────────────────────────────
# material_items
# ───────────────────────────────────────────────────────────────────────────
class MaterialItemIn(BaseModel):
    section_number: int | None = None
    kind: str = "material"
    name: str
    soll_qty: float | None = None
    ist_qty: float | None = None
    unit: str | None = None
    location: str | None = None
    status: str = "vorhanden"
    note: str | None = None


class MaterialItemOut(MaterialItemIn):
    id: int
    # Herkunfts-Felder für die Nachkalkulation (Read-only — werden beim
    # Anlegen via from-artikelstamm-Endpoint bzw. Offer-Sync gesetzt).
    source: str = "manual"
    artikelstamm_artikelnummer: str | None = None
    artikelstamm_preis_eur: float | None = None


@router.get("/{slug}/material-items", response_model=list[MaterialItemOut])
def list_material_items(slug: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    rows = (
        db.query(MaterialItem)
        .filter(MaterialItem.project_id == project.id)
        .order_by(MaterialItem.section_number, MaterialItem.kind, MaterialItem.name)
        .all()
    )
    return [
        MaterialItemOut(
            id=r.id, section_number=r.section_number, kind=r.kind, name=r.name,
            soll_qty=r.soll_qty, ist_qty=r.ist_qty, unit=r.unit, location=r.location,
            status=r.status, note=r.note,
            source=r.source, artikelstamm_artikelnummer=r.artikelstamm_artikelnummer,
            artikelstamm_preis_eur=r.artikelstamm_preis_eur,
        )
        for r in rows
    ]


@router.post("/{slug}/material-items", response_model=MaterialItemOut)
def create_material_item(slug: str, payload: MaterialItemIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    row = MaterialItem(project_id=project.id, user_id=current_user.id, **payload.dict())
    db.add(row)
    db.commit()
    db.refresh(row)
    _republish_sheets(db, slug)
    return MaterialItemOut(id=row.id, **payload.dict())


@router.patch("/{slug}/material-items/{item_id}", response_model=MaterialItemOut)
def update_material_item(slug: str, item_id: int, payload: MaterialItemIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    row = db.query(MaterialItem).filter(MaterialItem.id == item_id, MaterialItem.project_id == project.id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found")
    # ist_qty ist Aggregat aus material_usages — direkte Änderung wäre
    # nach der nächsten Verbrauchsbuchung verloren. Ignorieren und aus
    # echter Quelle rekonstruieren.
    updates = payload.dict()
    updates.pop("ist_qty", None)
    for k, v in updates.items():
        setattr(row, k, v)
    db.commit()
    # ist_qty aus usages re-aggregieren (Single Source of Truth).
    recalc_ist_qty(db, row.id)
    db.commit()
    db.refresh(row)
    _republish_sheets(db, slug)
    return MaterialItemOut(
        id=row.id,
        section_number=row.section_number,
        kind=row.kind,
        name=row.name,
        soll_qty=row.soll_qty,
        ist_qty=row.ist_qty,
        unit=row.unit,
        location=row.location,
        status=row.status,
        note=row.note,
    )


class BulkAssignSectionIn(BaseModel):
    item_ids: list[int]
    section_number: int | None = None  # None = wieder "nicht zugewiesen"


@router.post("/{slug}/material-items/bulk-assign-section")
def bulk_assign_section(
    slug: str,
    payload: BulkAssignSectionIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Weise mehrere material_items in einem Rutsch einem Bauabschnitt zu.
    Praktisch um nach einem Angebots-Upload alle Heizkörper-Positionen
    auf Abschnitt 3 zu schieben.
    """
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)

    if not payload.item_ids:
        return {"updated": 0}

    # Section validieren (None ist erlaubt = unassign)
    if payload.section_number is not None:
        section_exists = db.query(ProjectSection).filter(
            ProjectSection.project_id == project.id,
            ProjectSection.number == payload.section_number,
        ).first()
        if section_exists is None:
            raise HTTPException(status_code=404, detail=f"Section {payload.section_number} nicht in diesem Projekt")

    updated = (
        db.query(MaterialItem)
        .filter(MaterialItem.project_id == project.id, MaterialItem.id.in_(payload.item_ids))
        .update({MaterialItem.section_number: payload.section_number}, synchronize_session=False)
    )
    db.commit()
    _republish_sheets(db, slug)
    return {"updated": updated, "section_number": payload.section_number}


@router.delete("/{slug}/material-items/{item_id}")
def delete_material_item(slug: str, item_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    row = db.query(MaterialItem).filter(MaterialItem.id == item_id, MaterialItem.project_id == project.id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(row)
    db.commit()
    _republish_sheets(db, slug)
    return {"deleted": item_id}


# ───────────────────────────────────────────────────────────────────────────
# risk_issues
# ───────────────────────────────────────────────────────────────────────────
class RiskIssueIn(BaseModel):
    section_number: int | None = None
    kind: str = "risiko"
    description: str
    severity: str = "mittel"
    responsible: str | None = None
    status: str = "offen"
    due_date: _date | None = None


class RiskIssueOut(RiskIssueIn):
    id: int


@router.get("/{slug}/risk-issues", response_model=list[RiskIssueOut])
def list_risk_issues(slug: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    rows = (
        db.query(RiskIssue)
        .filter(RiskIssue.project_id == project.id)
        .order_by(RiskIssue.section_number, RiskIssue.created_at)
        .all()
    )
    return [RiskIssueOut(id=r.id, section_number=r.section_number, kind=r.kind, description=r.description, severity=r.severity, responsible=r.responsible, status=r.status, due_date=r.due_date) for r in rows]


@router.post("/{slug}/risk-issues", response_model=RiskIssueOut)
def create_risk_issue(slug: str, payload: RiskIssueIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    row = RiskIssue(project_id=project.id, user_id=current_user.id, **payload.dict())
    db.add(row)
    db.commit()
    db.refresh(row)
    return RiskIssueOut(id=row.id, **payload.dict())


@router.patch("/{slug}/risk-issues/{issue_id}", response_model=RiskIssueOut)
def update_risk_issue(slug: str, issue_id: int, payload: RiskIssueIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    row = db.query(RiskIssue).filter(RiskIssue.id == issue_id, RiskIssue.project_id == project.id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    for k, v in payload.dict().items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return RiskIssueOut(id=row.id, **payload.dict())


@router.delete("/{slug}/risk-issues/{issue_id}")
def delete_risk_issue(slug: str, issue_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    row = db.query(RiskIssue).filter(RiskIssue.id == issue_id, RiskIssue.project_id == project.id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    db.delete(row)
    db.commit()
    return {"deleted": issue_id}


# ───────────────────────────────────────────────────────────────────────────
# blockers (table already existed)
# ───────────────────────────────────────────────────────────────────────────
class BlockerIn(BaseModel):
    section_number: int | None = None
    description: str = Field(min_length=1)
    severity: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    status: str = Field(default="open", pattern="^(open|in_progress|done)$")


class BlockerOut(BlockerIn):
    id: int


@router.get("/{slug}/blockers", response_model=list[BlockerOut])
def list_blockers(slug: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    rows = (
        db.query(Blocker)
        .filter(Blocker.project_id == project.id)
        .order_by(Blocker.status, Blocker.section_number, Blocker.created_at.desc())
        .all()
    )
    return [BlockerOut(id=r.id, section_number=r.section_number, description=r.description, severity=r.severity, status=r.status) for r in rows]


@router.post("/{slug}/blockers", response_model=BlockerOut)
def create_blocker(slug: str, payload: BlockerIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    row = Blocker(project_id=project.id, user_id=current_user.id, **payload.dict())
    db.add(row)
    db.commit()
    db.refresh(row)
    return BlockerOut(id=row.id, **payload.dict())


@router.patch("/{slug}/blockers/{blocker_id}", response_model=BlockerOut)
def update_blocker(slug: str, blocker_id: int, payload: BlockerIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    row = db.query(Blocker).filter(Blocker.id == blocker_id, Blocker.project_id == project.id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Blocker not found")
    for k, v in payload.dict().items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return BlockerOut(id=row.id, **payload.dict())


@router.delete("/{slug}/blockers/{blocker_id}")
def delete_blocker(slug: str, blocker_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    row = db.query(Blocker).filter(Blocker.id == blocker_id, Blocker.project_id == project.id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Blocker not found")
    db.delete(row)
    db.commit()
    return {"deleted": blocker_id}


# ───────────────────────────────────────────────────────────────────────────
# Render templates to storage (ad-hoc, ohne Codex-Run)
# ───────────────────────────────────────────────────────────────────────────
class TemplatePublishOut(BaseModel):
    slug: str
    category: str
    relative_path: str
    bytes_written: int


@router.post("/{slug}/render-templates", response_model=list[TemplatePublishOut])
def render_templates(slug: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Render every DB template for this project and overwrite the static
    HTMLs under storage/projects/<slug>/. Idempotent — re-run safely."""
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    results = template_publisher.publish_templates_to_storage(db, slug)
    return [
        TemplatePublishOut(slug=r.slug, category=r.category, relative_path=r.relative_path, bytes_written=r.bytes_written)
        for r in results
    ]


# ───────────────────────────────────────────────────────────────────────────
# material_usages — Verbrauchsbuchungen (pro Daily-Report oder ad-hoc)
# ───────────────────────────────────────────────────────────────────────────
class MaterialUsageIn(BaseModel):
    material_item_id: int
    daily_report_id: int | None = None
    section_number: int | None = None
    qty_used: float = Field(gt=0)
    unit: str | None = None
    used_at: _date
    notes: str | None = None


class MaterialUsageOut(BaseModel):
    id: int
    material_item_id: int | None
    material_item_name: str | None
    daily_report_id: int | None
    user_id: int | None
    username: str | None
    section_number: int | None
    qty_used: float
    unit: str | None
    used_at: _date
    notes: str | None
    created_at: str


def _usage_out(u: MaterialUsage, item: MaterialItem | None, user: User | None) -> MaterialUsageOut:
    return MaterialUsageOut(
        id=u.id,
        material_item_id=u.material_item_id,
        material_item_name=item.name if item else None,
        daily_report_id=u.daily_report_id,
        user_id=u.user_id,
        username=user.username if user else None,
        section_number=u.section_number,
        qty_used=u.qty_used,
        unit=u.unit,
        used_at=u.used_at,
        notes=u.notes,
        created_at=u.created_at.isoformat() if u.created_at else "",
    )


@router.get("/{slug}/material-usages", response_model=list[MaterialUsageOut])
def list_material_usages(
    slug: str,
    material_item_id: int | None = None,
    daily_report_id: int | None = None,
    von: _date | None = None,
    bis: _date | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    q = db.query(MaterialUsage).filter(MaterialUsage.project_id == project.id)
    if material_item_id is not None:
        q = q.filter(MaterialUsage.material_item_id == material_item_id)
    if daily_report_id is not None:
        q = q.filter(MaterialUsage.daily_report_id == daily_report_id)
    if von is not None:
        q = q.filter(MaterialUsage.used_at >= von)
    if bis is not None:
        q = q.filter(MaterialUsage.used_at <= bis)
    rows = q.order_by(MaterialUsage.used_at.desc(), MaterialUsage.id.desc()).all()

    item_ids = {r.material_item_id for r in rows if r.material_item_id}
    user_ids = {r.user_id for r in rows if r.user_id}
    items = {i.id: i for i in db.query(MaterialItem).filter(MaterialItem.id.in_(item_ids)).all()} if item_ids else {}
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    return [_usage_out(r, items.get(r.material_item_id), users.get(r.user_id)) for r in rows]


@router.post("/{slug}/material-usages", response_model=MaterialUsageOut)
def create_material_usage(
    slug: str,
    payload: MaterialUsageIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _load_project(db, slug)
    # Monteur darf eigenen Verbrauch buchen (gehört zum Tagesbericht).
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    item = db.query(MaterialItem).filter(
        MaterialItem.id == payload.material_item_id,
        MaterialItem.project_id == project.id,
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="material_item not found in this project")

    if payload.daily_report_id is not None:
        dr = db.query(DailyReport).filter(
            DailyReport.id == payload.daily_report_id,
            DailyReport.project_id == project.id,
        ).first()
        if dr is None:
            raise HTTPException(status_code=404, detail="daily_report not found in this project")

    # section_number aus material_item übernehmen, wenn nicht explizit gesetzt
    section_number = payload.section_number if payload.section_number is not None else item.section_number
    unit = payload.unit or item.unit

    # Auto-Assign: wenn der User in einem Abschnitt verbucht und das Material
    # noch keinem Abschnitt zugewiesen ist, übernehme die Zuweisung.
    # Verhindert dass das Item dauerhaft im "Nicht zugewiesen"-Akkordeon liegt.
    if item.section_number is None and payload.section_number is not None:
        item.section_number = payload.section_number

    row = MaterialUsage(
        project_id=project.id,
        material_item_id=item.id,
        daily_report_id=payload.daily_report_id,
        user_id=current_user.id,
        section_number=section_number,
        qty_used=payload.qty_used,
        unit=unit,
        used_at=payload.used_at,
        notes=payload.notes,
    )
    db.add(row)
    db.flush()
    recalc_ist_qty(db, item.id)
    db.commit()
    db.refresh(row)
    _republish_sheets(db, slug)
    return _usage_out(row, item, current_user)


@router.delete("/{slug}/material-usages/{usage_id}")
def delete_material_usage(
    slug: str,
    usage_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _load_project(db, slug)
    role = require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    row = db.query(MaterialUsage).filter(
        MaterialUsage.id == usage_id,
        MaterialUsage.project_id == project.id,
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Usage not found")
    # Monteur darf nur EIGENE Buchungen löschen, Lead-Rollen alle.
    if role == "monteur" and row.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Nur eigene Buchungen löschbar")
    item_id = row.material_item_id
    db.delete(row)
    db.flush()
    if item_id is not None:
        recalc_ist_qty(db, item_id)
    db.commit()
    _republish_sheets(db, slug)
    return {"deleted": usage_id}


# ───────────────────────────────────────────────────────────────────────────
# milestones — abgeleitete Projekt-Meilensteine
# ───────────────────────────────────────────────────────────────────────────
class MilestoneOut(BaseModel):
    id: int
    type: str
    title: str
    description: str | None
    planned_date: _date | None
    actual_date: _date | None
    status: str
    section_id: int | None


@router.get("/{slug}/milestones", response_model=list[MilestoneOut])
def list_milestones(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    from app.services.milestones import list_milestones_for_render
    return [MilestoneOut(**m) for m in list_milestones_for_render(db, project.id)]


@router.post("/{slug}/milestones/sync")
def sync_milestones_endpoint(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    from app.services.milestones import sync_milestones
    return sync_milestones(db, project.id)


# ───────────────────────────────────────────────────────────────────────────
# material-consistency — Drift-Check und Self-Healing
# ───────────────────────────────────────────────────────────────────────────
class MaterialDriftOut(BaseModel):
    material_item_id: int
    name: str
    stored_ist: float
    computed_ist: float
    delta: float


@router.get("/{slug}/material-consistency", response_model=list[MaterialDriftOut])
def material_consistency(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Liste der material_items, deren gespeicherte ist_qty von der Summe
    aller usages abweicht. Leere Liste = alles konsistent."""
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    from app.services.material_usage import find_material_drift
    return [MaterialDriftOut(**d) for d in find_material_drift(db, project.id)]


@router.post("/{slug}/material-recalc-all")
def material_recalc_all(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Erzwinge ist_qty = SUM(usages) für alle gedrifteten material_items."""
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    from app.services.material_usage import heal_material_drift
    stats = heal_material_drift(db, project.id)
    db.commit()
    return stats
