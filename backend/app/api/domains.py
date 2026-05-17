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
    MaterialItem,
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


router = APIRouter()


def _load_project(db: Session, slug: str) -> Project:
    project = db.query(Project).filter(Project.slug == slug).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


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
    return [MaterialItemOut(id=r.id, section_number=r.section_number, kind=r.kind, name=r.name, soll_qty=r.soll_qty, ist_qty=r.ist_qty, unit=r.unit, location=r.location, status=r.status, note=r.note) for r in rows]


@router.post("/{slug}/material-items", response_model=MaterialItemOut)
def create_material_item(slug: str, payload: MaterialItemIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    row = MaterialItem(project_id=project.id, user_id=current_user.id, **payload.dict())
    db.add(row)
    db.commit()
    db.refresh(row)
    return MaterialItemOut(id=row.id, **payload.dict())


@router.patch("/{slug}/material-items/{item_id}", response_model=MaterialItemOut)
def update_material_item(slug: str, item_id: int, payload: MaterialItemIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    row = db.query(MaterialItem).filter(MaterialItem.id == item_id, MaterialItem.project_id == project.id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found")
    for k, v in payload.dict().items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return MaterialItemOut(id=row.id, **payload.dict())


@router.delete("/{slug}/material-items/{item_id}")
def delete_material_item(slug: str, item_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = _load_project(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    row = db.query(MaterialItem).filter(MaterialItem.id == item_id, MaterialItem.project_id == project.id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(row)
    db.commit()
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
