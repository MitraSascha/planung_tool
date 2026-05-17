from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.orm_models import Blocker, DailyReport, MaterialIssue, Project, ProjectMember, User, WeeklyReport
from app.models.anomalies import (
    AnomalyRead,
    WeeklyReportDraftRead,
    WeeklyReportDraftRequest,
)
from app.models.auth import ProjectMemberCreate, ProjectMemberRead
from app.models.reports import (
    BlockerCreate,
    BlockerRead,
    BlockerUpdate,
    DailyReportCreate,
    DailyReportRead,
    MaterialIssueCreate,
    MaterialIssueRead,
    MaterialIssueUpdate,
    ReportSummary,
    WeeklyReportCreate,
    WeeklyReportRead,
)
from app.services.anomaly_detector import detect_project_anomalies
from app.services.auth import (
    ADMIN_ROLES,
    PROJECT_READ_ROLES,
    SITE_LEAD_ROLES,
    get_current_user,
    require_global_role,
    require_project_role,
)
from app.services.weekly_report_drafter import build_deterministic_draft, draft_weekly_report

router = APIRouter()


def _project_or_404(db: Session, slug: str) -> Project:
    project = db.query(Project).filter(Project.slug == slug).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _daily_read(report: DailyReport) -> DailyReportRead:
    return DailyReportRead(
        id=report.id,
        project_slug=report.project.slug,
        user_id=report.user_id,
        username=report.user.username,
        display_name=report.user.display_name,
        section_number=report.section_number,
        report_date=report.report_date,
        status=report.status,
        team=report.team,
        completed_work=report.completed_work,
        open_work=report.open_work,
        material_missing=report.material_missing,
        blockers=report.blockers,
        notes=report.notes,
        ist_hours=report.ist_hours,
        safety_psa=report.safety_psa,
        safety_tools=report.safety_tools,
        safety_material=report.safety_material,
        safety_workarea=report.safety_workarea,
        safety_approval=report.safety_approval,
        created_at=report.created_at,
    )


def _weekly_read(report: WeeklyReport) -> WeeklyReportRead:
    return WeeklyReportRead(
        id=report.id,
        project_slug=report.project.slug,
        user_id=report.user_id,
        username=report.user.username,
        display_name=report.user.display_name,
        week_start=report.week_start,
        week_end=report.week_end,
        status=report.status,
        summary=report.summary,
        next_week_plan=report.next_week_plan,
        manpower_notes=report.manpower_notes,
        material_notes=report.material_notes,
        risks=report.risks,
        created_at=report.created_at,
    )


@router.get("/projects/{slug}/members", response_model=list[ProjectMemberRead])
def list_project_members(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProjectMemberRead]:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    members = db.query(ProjectMember).filter(ProjectMember.project_id == project.id).all()
    return [
        ProjectMemberRead(
            id=member.id,
            user_id=member.user_id,
            username=member.user.username,
            display_name=member.user.display_name,
            project_role=member.project_role,
        )
        for member in members
    ]


@router.post("/projects/{slug}/members", response_model=ProjectMemberRead)
def add_project_member(
    slug: str,
    request: ProjectMemberCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectMemberRead:
    project = _project_or_404(db, slug)
    require_global_role(current_user, ADMIN_ROLES)

    user = db.query(User).filter(User.id == request.user_id, User.active.is_(True)).one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    existing = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project.id, ProjectMember.user_id == user.id)
        .one_or_none()
    )
    if existing is not None:
        existing.project_role = request.project_role
        member = existing
    else:
        member = ProjectMember(project_id=project.id, user_id=user.id, project_role=request.project_role)
        db.add(member)

    db.commit()
    db.refresh(member)
    return ProjectMemberRead(
        id=member.id,
        user_id=member.user_id,
        username=user.username,
        display_name=user.display_name,
        project_role=member.project_role,
    )


@router.post("/projects/{slug}/daily-reports", response_model=DailyReportRead)
def create_daily_report(
    slug: str,
    request: DailyReportCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DailyReportRead:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    report = DailyReport(project_id=project.id, user_id=current_user.id, **request.model_dump())
    db.add(report)
    db.commit()
    db.refresh(report)
    return _daily_read(report)


@router.get("/projects/{slug}/daily-reports", response_model=list[DailyReportRead])
def list_daily_reports(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DailyReportRead]:
    project = _project_or_404(db, slug)
    role = require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    query = db.query(DailyReport).filter(DailyReport.project_id == project.id)
    if role == "monteur":
        query = query.filter(DailyReport.user_id == current_user.id)
    reports = query.order_by(DailyReport.report_date.desc(), DailyReport.created_at.desc()).all()
    return [_daily_read(report) for report in reports]


@router.post("/projects/{slug}/weekly-reports", response_model=WeeklyReportRead)
def create_weekly_report(
    slug: str,
    request: WeeklyReportCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WeeklyReportRead:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    report = WeeklyReport(project_id=project.id, user_id=current_user.id, **request.model_dump())
    db.add(report)
    db.commit()
    db.refresh(report)
    return _weekly_read(report)


@router.get("/projects/{slug}/weekly-reports", response_model=list[WeeklyReportRead])
def list_weekly_reports(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WeeklyReportRead]:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    reports = db.query(WeeklyReport).filter(WeeklyReport.project_id == project.id).order_by(WeeklyReport.week_start.desc()).all()
    return [_weekly_read(report) for report in reports]


def _material_read(issue: MaterialIssue) -> MaterialIssueRead:
    return MaterialIssueRead(
        id=issue.id,
        project_slug=issue.project.slug,
        user_id=issue.user_id,
        username=issue.user.username,
        display_name=issue.user.display_name,
        section_number=issue.section_number,
        description=issue.description,
        priority=issue.priority,
        status=issue.status,
        created_at=issue.created_at,
    )


def _blocker_read(blocker: Blocker) -> BlockerRead:
    return BlockerRead(
        id=blocker.id,
        project_slug=blocker.project.slug,
        user_id=blocker.user_id,
        username=blocker.user.username,
        display_name=blocker.user.display_name,
        section_number=blocker.section_number,
        description=blocker.description,
        severity=blocker.severity,
        status=blocker.status,
        created_at=blocker.created_at,
    )


@router.post("/projects/{slug}/material-issues", response_model=MaterialIssueRead)
def create_material_issue(
    slug: str,
    request: MaterialIssueCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MaterialIssueRead:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    issue = MaterialIssue(project_id=project.id, user_id=current_user.id, **request.model_dump())
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return _material_read(issue)


@router.get("/projects/{slug}/material-issues", response_model=list[MaterialIssueRead])
def list_material_issues(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MaterialIssueRead]:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    issues = (
        db.query(MaterialIssue)
        .filter(MaterialIssue.project_id == project.id)
        .order_by(MaterialIssue.created_at.desc())
        .all()
    )
    return [_material_read(issue) for issue in issues]


@router.patch("/projects/{slug}/material-issues/{issue_id}", response_model=MaterialIssueRead)
def update_material_issue(
    slug: str,
    issue_id: int,
    request: MaterialIssueUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MaterialIssueRead:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    issue = (
        db.query(MaterialIssue)
        .filter(MaterialIssue.id == issue_id, MaterialIssue.project_id == project.id)
        .one_or_none()
    )
    if issue is None:
        raise HTTPException(status_code=404, detail="Material issue not found")
    issue.status = request.status
    db.commit()
    db.refresh(issue)
    return _material_read(issue)


@router.post("/projects/{slug}/blockers", response_model=BlockerRead)
def create_blocker(
    slug: str,
    request: BlockerCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BlockerRead:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    blocker = Blocker(project_id=project.id, user_id=current_user.id, **request.model_dump())
    db.add(blocker)
    db.commit()
    db.refresh(blocker)
    return _blocker_read(blocker)


@router.get("/projects/{slug}/blockers", response_model=list[BlockerRead])
def list_blockers(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[BlockerRead]:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    blockers = (
        db.query(Blocker)
        .filter(Blocker.project_id == project.id)
        .order_by(Blocker.created_at.desc())
        .all()
    )
    return [_blocker_read(blocker) for blocker in blockers]


@router.patch("/projects/{slug}/blockers/{blocker_id}", response_model=BlockerRead)
def update_blocker(
    slug: str,
    blocker_id: int,
    request: BlockerUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BlockerRead:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    blocker = (
        db.query(Blocker)
        .filter(Blocker.id == blocker_id, Blocker.project_id == project.id)
        .one_or_none()
    )
    if blocker is None:
        raise HTTPException(status_code=404, detail="Blocker not found")
    blocker.status = request.status
    db.commit()
    db.refresh(blocker)
    return _blocker_read(blocker)


@router.post(
    "/projects/{slug}/weekly-reports/draft",
    response_model=WeeklyReportDraftRead,
)
async def draft_weekly_report_endpoint(
    slug: str,
    request: WeeklyReportDraftRequest,
    mode: str = "quick",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WeeklyReportDraftRead:
    """Draft a weekly report from the daily reports of the given week.

    ``mode``:
    - ``"quick"`` (default): deterministische Aggregation, instant, kein
      LLM-Call. Liest alle daily_reports der Woche, joint completed_work,
      open_work, material_missing, blockers; setzt Status nach worst-case.
    - ``"llm"``: LLM-Polishing on top (Codex/Claude). Dauert sekunden,
      kostet Token, produziert "menschlicheren" Text.

    Nicht persistiert — die Antwort wird ins Frontend-Formular vorbefüllt,
    der User reviewt und speichert explizit via ``POST /weekly-reports``.
    """
    from app.db.orm_models import DailyReport
    from sqlalchemy.orm import selectinload
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)

    if mode == "llm":
        draft = await draft_weekly_report(db, project, request.week_start, request.week_end)
    else:
        # quick / deterministic — keine LLM-Latenz, kein Token-Verbrauch.
        # selectinload(user), damit der Drafter Display-Name + Stunden pro
        # Autor zuordnen kann.
        reports = (
            db.query(DailyReport)
            .options(selectinload(DailyReport.user))
            .filter(
                DailyReport.project_id == project.id,
                DailyReport.report_date >= request.week_start,
                DailyReport.report_date <= request.week_end,
            )
            .order_by(DailyReport.report_date)
            .all()
        )
        draft = build_deterministic_draft(reports)

    return WeeklyReportDraftRead(
        summary=draft.summary,
        next_week_plan=draft.next_week_plan,
        manpower_notes=draft.manpower_notes,
        material_notes=draft.material_notes,
        risks=draft.risks,
        status=draft.status if draft.status in {"green", "yellow", "red"} else "green",
    )


def _anomalies_for_project(db: Session, project: Project) -> list[AnomalyRead]:
    return [
        AnomalyRead(
            project_slug=a.project_slug,
            kind=a.kind,
            severity=a.severity,
            title=a.title,
            detail=a.detail,
            related_ids=a.related_ids,
            detected_at=a.detected_at,
        )
        for a in detect_project_anomalies(db, project)
    ]


@router.get("/projects/{slug}/anomalies", response_model=list[AnomalyRead])
def list_project_anomalies(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AnomalyRead]:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    return _anomalies_for_project(db, project)


@router.get("/anomalies", response_model=list[AnomalyRead])
def list_all_anomalies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AnomalyRead]:
    """All anomalies across every project the current user has access to.

    Admins / project leads see every project; everyone else is filtered
    via their ``ProjectMember`` rows.
    """
    if current_user.global_role in ADMIN_ROLES:
        projects = db.query(Project).all()
    else:
        memberships = (
            db.query(ProjectMember)
            .filter(ProjectMember.user_id == current_user.id)
            .all()
        )
        project_ids = [m.project_id for m in memberships]
        if not project_ids:
            return []
        projects = db.query(Project).filter(Project.id.in_(project_ids)).all()

    out: list[AnomalyRead] = []
    for project in projects:
        out.extend(_anomalies_for_project(db, project))
    return out


@router.get("/projects/{slug}/summary", response_model=ReportSummary)
def report_summary(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportSummary:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    daily_reports = db.query(DailyReport).filter(DailyReport.project_id == project.id).all()
    return ReportSummary(
        project_slug=slug,
        daily_reports=len(daily_reports),
        weekly_reports=db.query(WeeklyReport).filter(WeeklyReport.project_id == project.id).count(),
        material_issues_open=db.query(MaterialIssue).filter(MaterialIssue.project_id == project.id, MaterialIssue.status == "open").count(),
        blockers_open=db.query(Blocker).filter(Blocker.project_id == project.id, Blocker.status == "open").count(),
        status_green=sum(1 for report in daily_reports if report.status == "green"),
        status_yellow=sum(1 for report in daily_reports if report.status == "yellow"),
        status_red=sum(1 for report in daily_reports if report.status == "red"),
    )
