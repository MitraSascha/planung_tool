from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.orm_models import Blocker, DailyReport, MaterialIssue, Project, ProjectMember, User, WeeklyReport
from app.models.auth import ProjectMemberCreate, ProjectMemberRead
from app.models.reports import (
    BlockerCreate,
    DailyReportCreate,
    DailyReportRead,
    MaterialIssueCreate,
    ReportSummary,
    WeeklyReportCreate,
    WeeklyReportRead,
)
from app.services.auth import (
    ADMIN_ROLES,
    PROJECT_READ_ROLES,
    SITE_LEAD_ROLES,
    get_current_user,
    require_global_role,
    require_project_role,
)

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

    if request.material_missing:
        db.add(
            MaterialIssue(
                project_id=project.id,
                user_id=current_user.id,
                section_number=request.section_number,
                description=request.material_missing,
                priority="normal",
            )
        )
    if request.blockers:
        db.add(
            Blocker(
                project_id=project.id,
                user_id=current_user.id,
                section_number=request.section_number,
                description=request.blockers,
                severity="medium",
            )
        )

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


@router.post("/projects/{slug}/material-issues")
def create_material_issue(
    slug: str,
    request: MaterialIssueCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    issue = MaterialIssue(project_id=project.id, user_id=current_user.id, **request.model_dump())
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return {"id": issue.id}


@router.post("/projects/{slug}/blockers")
def create_blocker(
    slug: str,
    request: BlockerCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    blocker = Blocker(project_id=project.id, user_id=current_user.id, **request.model_dump())
    db.add(blocker)
    db.commit()
    db.refresh(blocker)
    return {"id": blocker.id}


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
