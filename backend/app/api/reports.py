from datetime import date as _date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.orm_models import Blocker, DailyReport, DailyReportAttendee, MaterialIssue, Project, ProjectMember, User, WeeklyReport
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
    DailyReportUpdate,
    MaterialIssueCreate,
    MaterialIssueProcurementUpdate,
    MaterialIssueRead,
    MaterialIssueUpdate,
    ReportSummary,
    WeeklyReportCreate,
    WeeklyReportRead,
)
from app.services.anomaly_detector import detect_project_anomalies
from app.services.arbeitstagerfassung import split_arbeitstagerfassung
from app.services.auth import (
    ADMIN_ROLES,
    PROJECT_READ_ROLES,
    SITE_LEAD_ROLES,
    get_current_user,
    require_global_role,
    require_project_role,
)
from app.services import template_publisher
from app.services.weekly_report_drafter import build_deterministic_draft, draft_weekly_report


def _republish_sheets(db: Session, slug: str) -> None:
    """Re-render der HTML-Sheets nach Tagesbericht-Mutation, damit Teamstatus/
    Stunden-Aggregate sofort auf dem aktuellen Stand sind. Best-effort —
    Render-Fehler dürfen die Haupt-Operation nicht abbrechen."""
    try:
        template_publisher.publish_templates_to_storage(db, slug)
    except Exception:
        pass

# Tagesbericht-Edit-Fenster: Eigentümer dürfen ihren Bericht am Erstellungs-
# und am Folgetag noch nachbearbeiten. Danach friert er ein (Audit-Trail).
DAILY_REPORT_EDIT_WINDOW_DAYS = 1
# Rollen, die Berichte auch außerhalb des Edit-Fensters bzw. fremde
# Berichte editieren dürfen (Tippfehler-Korrektur durch die Bauleitung).
DAILY_REPORT_OVERRIDE_ROLES = frozenset({"admin", "projektleitung", "bauleitung"})

router = APIRouter()


def _project_or_404(db: Session, slug: str) -> Project:
    project = db.query(Project).filter(Project.slug == slug).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _sync_open_point_from_daily(
    db: Session,
    report: DailyReport,
    field: str,
    new_value: str | None,
    *,
    is_update: bool,
) -> None:
    """Auto-Sync von ``DailyReport.material_missing`` / ``.blockers`` in
    die jeweiligen Open-Points-Tabellen (``MaterialIssue`` / ``Blocker``).

    Semantik (siehe README/Open-Points-Konzept):

    - **create** und non-leerer Text -> neue Zeile mit
      ``source_daily_report_id = report.id``.
    - **update** und non-leerer Text -> existierende offene Zeile mit
      gleichem source-FK updaten (Description). Wenn keine offene Zeile
      existiert (z.B. weil sie schon geschlossen wurde) -> neue Zeile
      anlegen.
    - **update** und leerer Text -> bestehende offene Zeile nicht löschen,
      sondern Status auf ``done`` setzen (der Monteur hat das Problem
      rausgenommen = ist erledigt). So bleibt die Historie erhalten.

    Truthiness: nur nicht-whitespace gilt als "vorhanden".
    """
    text = (new_value or "").strip()

    if field == "material_missing":
        Model = MaterialIssue
        kind_kwargs = {"priority": "normal"}
    elif field == "blockers":
        Model = Blocker
        kind_kwargs = {"severity": "medium"}
    else:  # pragma: no cover - defensive
        return

    if not text:
        # Nur beim Update relevant — beim Create gibt es nichts zu schließen.
        if not is_update:
            return
        open_row = (
            db.query(Model)
            .filter(
                Model.source_daily_report_id == report.id,
                Model.status == "open",
            )
            .one_or_none()
        )
        if open_row is not None:
            open_row.status = "done"
        return

    # Non-leerer Text — beim Update vorhandene offene Zeile finden,
    # sonst neu anlegen.
    open_row = None
    if is_update:
        open_row = (
            db.query(Model)
            .filter(
                Model.source_daily_report_id == report.id,
                Model.status == "open",
            )
            .one_or_none()
        )
    if open_row is not None:
        open_row.description = text
        return

    db.add(
        Model(
            project_id=report.project_id,
            user_id=report.user_id,
            section_number=report.section_number,
            description=text,
            source_daily_report_id=report.id,
            **kind_kwargs,
        )
    )


def _daily_can_edit(report: DailyReport, user: User, role: str) -> bool:
    """Owner darf bis ``DAILY_REPORT_EDIT_WINDOW_DAYS`` nach ``report_date``
    nachbearbeiten; Override-Rollen dürfen jederzeit."""
    if role in DAILY_REPORT_OVERRIDE_ROLES:
        return True
    if report.user_id != user.id:
        return False
    today = _date.today()
    return (today - report.report_date).days <= DAILY_REPORT_EDIT_WINDOW_DAYS


def _daily_read(report: DailyReport, editable: bool = False) -> DailyReportRead:
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
        attendee_user_ids=[a.user_id for a in report.attendees],
        completed_work=report.completed_work,
        open_work=report.open_work,
        raw_work_log=report.raw_work_log,
        raw_work_log_language=report.raw_work_log_language,
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
        editable=editable,
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
    # Jeder Projekt-Mitarbeiter darf das Team sehen (Tagesbericht-Wizard
    # nutzt das für die Anwesenheits-Auswahl). Schreiben bleibt Leads.
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
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
    payload = request.model_dump()
    attendee_ids = payload.pop("attendee_user_ids", []) or []
    # Ersteller automatisch als anwesend dazunehmen, sofern attendees gepflegt
    # werden (= moderner Wizard-Flow). Override: wenn der User sich explizit
    # raus genommen hat und keine attendees sendet, lassen wir die Liste leer
    # (Edge-Case: Büro schreibt stellvertretend — dann muss er aber wenigstens
    # einen anderen User angeben, sonst fällt der Bericht aus der
    # Teamstatus-Matrix raus). Wenn attendee_ids leer kommt, ergänzen wir nicht
    # — der User nutzt vermutlich noch das Freitext-Team-Feld.
    if attendee_ids and current_user.id not in attendee_ids:
        attendee_ids = [*attendee_ids, current_user.id]
    # Arbeitstagerfassung: wenn der Monteur das Roh-Feld benutzt hat, splittet
    # ein LLM in Erledigt/Offen. Roh-Text bleibt persistent. Bei Bestands-
    # Workflow (separate Felder) wird der Service gar nicht erst gerufen.
    raw_text = (payload.get("raw_work_log") or "").strip()
    if raw_text:
        split = split_arbeitstagerfassung(
            raw_text, source_language=payload.get("raw_work_log_language")
        )
        # Nur überschreiben wenn der Split was Brauchbares geliefert hat —
        # sonst gewinnt das was der User in completed/open explizit getippt
        # haben könnte.
        if split.completed or split.pending:
            payload["completed_work"] = split.completed or None
            payload["open_work"] = split.pending or None
        if split.detected_language and not payload.get("raw_work_log_language"):
            payload["raw_work_log_language"] = split.detected_language
    report = DailyReport(project_id=project.id, user_id=current_user.id, **payload)
    db.add(report)
    db.flush()
    # Auto-Sync: Freitext-Felder in das Open-Points-Tracking schreiben,
    # damit die Bauleitung Material-/Blocker-Meldungen aus dem Bericht
    # nicht übersieht (vorher musste der Bericht selbst geöffnet werden).
    _sync_open_point_from_daily(
        db, report, "material_missing", report.material_missing, is_update=False
    )
    _sync_open_point_from_daily(
        db, report, "blockers", report.blockers, is_update=False
    )
    # Attendees nur für User anlegen, die wirklich Projekt-Mitglieder sind.
    if attendee_ids:
        valid_member_ids = {
            row[0]
            for row in db.query(ProjectMember.user_id)
            .filter(ProjectMember.project_id == project.id, ProjectMember.user_id.in_(attendee_ids))
            .all()
        }
        for uid in valid_member_ids:
            db.add(DailyReportAttendee(daily_report_id=report.id, user_id=uid))
    db.commit()
    db.refresh(report)
    _republish_sheets(db, slug)
    return _daily_read(report, editable=_daily_can_edit(report, current_user, "monteur"))


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
    return [_daily_read(r, editable=_daily_can_edit(r, current_user, role)) for r in reports]


@router.patch("/projects/{slug}/daily-reports/{report_id}", response_model=DailyReportRead)
def update_daily_report(
    slug: str,
    report_id: int,
    request: DailyReportUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DailyReportRead:
    """Tagesbericht nachbearbeiten — Owner bis Folgetag, Leads ohne Limit.

    Versehentlich Vergessenes nachtragen ist der Hauptgrund. Datum und
    Owner sind nicht änderbar; alle inhaltlichen Felder sind optional und
    überschreiben nur, was im Payload mitkommt.
    """
    project = _project_or_404(db, slug)
    role = require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    report = (
        db.query(DailyReport)
        .filter(DailyReport.id == report_id, DailyReport.project_id == project.id)
        .one_or_none()
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Daily report not found")

    if not _daily_can_edit(report, current_user, role):
        cutoff = report.report_date + timedelta(days=DAILY_REPORT_EDIT_WINDOW_DAYS)
        raise HTTPException(
            status_code=403,
            detail=(
                "Bearbeitung nicht erlaubt: entweder fremder Bericht oder "
                f"Edit-Fenster (bis {cutoff.isoformat()}) abgelaufen."
            ),
        )

    payload = request.model_dump(exclude_unset=True)
    attendee_ids = payload.pop("attendee_user_ids", None)
    # Wenn der Edit den Roh-Text der Arbeitstagerfassung ändert, neuen Split
    # ausführen — analog zum Create-Flow. Edits am Roh-Text ohne expliziten
    # completed/open-Override sollen die abgeleiteten Felder mit-aktualisieren.
    if "raw_work_log" in payload:
        raw_text = (payload.get("raw_work_log") or "").strip()
        if raw_text:
            split = split_arbeitstagerfassung(
                raw_text,
                source_language=payload.get("raw_work_log_language")
                or report.raw_work_log_language,
            )
            if split.completed or split.pending:
                # Explizit gesetzte Werte im selben Patch haben Vorrang.
                if "completed_work" not in payload:
                    payload["completed_work"] = split.completed or None
                if "open_work" not in payload:
                    payload["open_work"] = split.pending or None
            if split.detected_language and not payload.get("raw_work_log_language"):
                payload["raw_work_log_language"] = split.detected_language
    for field, value in payload.items():
        setattr(report, field, value)

    # Auto-Sync der beiden Freitext-Felder ins Open-Points-Tracking.
    # Nur wenn das Feld tatsächlich im Payload kam — sonst gilt "nicht
    # angefasst" und wir tasten weder eine offene noch eine geschlossene
    # Zeile an.
    if "material_missing" in payload:
        _sync_open_point_from_daily(
            db, report, "material_missing", payload["material_missing"], is_update=True
        )
    if "blockers" in payload:
        _sync_open_point_from_daily(
            db, report, "blockers", payload["blockers"], is_update=True
        )

    if attendee_ids is not None:
        # Komplette Ersetzung der Anwesenheits-Liste.
        db.query(DailyReportAttendee).filter(
            DailyReportAttendee.daily_report_id == report.id
        ).delete(synchronize_session=False)
        if attendee_ids:
            valid_member_ids = {
                row[0]
                for row in db.query(ProjectMember.user_id)
                .filter(
                    ProjectMember.project_id == project.id,
                    ProjectMember.user_id.in_(attendee_ids),
                )
                .all()
            }
            for uid in valid_member_ids:
                db.add(DailyReportAttendee(daily_report_id=report.id, user_id=uid))

    db.commit()
    db.refresh(report)
    _republish_sheets(db, slug)
    return _daily_read(report, editable=_daily_can_edit(report, current_user, role))


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
        procurement_status=issue.procurement_status,
        ordered_at=issue.ordered_at,
        ordered_by_username=(
            issue.ordered_by.username if issue.ordered_by is not None else None
        ),
        shipped_at=issue.shipped_at,
        shipped_by_username=(
            issue.shipped_by.username if issue.shipped_by is not None else None
        ),
        arrived_at=issue.arrived_at,
        arrived_by_username=(
            issue.arrived_by.username if issue.arrived_by is not None else None
        ),
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


@router.get("/material-issues/all", response_model=list[MaterialIssueRead])
def list_all_material_issues(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MaterialIssueRead]:
    """Bündel-Liste über alle Projekte hinweg, in denen der User mitarbeitet.

    Lead-Rollen (admin, projektleitung) sehen alles. Bauleitung/Obermonteur/
    Monteur sehen nur Issues aus Projekten, in denen sie Mitglied sind. So
    sieht ein Monteur seine eigenen Meldungen wieder, Bauleitung sieht das,
    was sie überwachen muss — ohne pro Projekt neu klicken zu müssen.
    """
    base = (
        db.query(MaterialIssue)
        .join(Project, MaterialIssue.project_id == Project.id)
        .order_by(MaterialIssue.created_at.desc())
    )
    # Globale Lead-Rollen sehen alle Projekte; sonst nur die mit Mitgliedschaft.
    if current_user.global_role in {"admin", "projektleitung"}:
        issues = base.all()
    else:
        visible_project_ids = {
            row[0]
            for row in db.query(ProjectMember.project_id)
            .filter(ProjectMember.user_id == current_user.id)
            .all()
        }
        if not visible_project_ids:
            return []
        issues = base.filter(MaterialIssue.project_id.in_(visible_project_ids)).all()
    return [_material_read(issue) for issue in issues]


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


@router.patch(
    "/projects/{slug}/material-issues/{issue_id}/procurement",
    response_model=MaterialIssueRead,
)
def update_material_issue_procurement(
    slug: str,
    issue_id: int,
    request: MaterialIssueProcurementUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MaterialIssueRead:
    """Beschaffungs-Stepper (Offen -> Bestellt -> Unterwegs -> Angekommen).

    Setzt den ``procurement_status`` UND stempelt — falls die jeweilige
    Stufe noch nicht gestempelt war — Timestamp + User auf der passenden
    Audit-Spalte. Bestehende Audit-Stempel werden NIE zurückgenommen,
    auch wenn der Status zurückgesetzt wird (Audit-Trail bleibt erhalten).
    """
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    issue = (
        db.query(MaterialIssue)
        .filter(MaterialIssue.id == issue_id, MaterialIssue.project_id == project.id)
        .one_or_none()
    )
    if issue is None:
        raise HTTPException(status_code=404, detail="Material issue not found")

    new_status = request.procurement_status
    issue.procurement_status = new_status

    # Linearer Stempel: nur die explizit gesetzte Stufe bekommt Timestamp
    # + User. Frühere Stufen bleiben unverändert (Audit). Re-Klick auf
    # bereits gestempelte Stufe überschreibt den Stempel NICHT.
    from sqlalchemy import func as _func  # lokaler Import, kein Top-Level-Bedarf
    now = _func.now()
    if new_status == "bestellt" and issue.ordered_at is None:
        issue.ordered_at = now
        issue.ordered_by_user_id = current_user.id
    elif new_status == "unterwegs" and issue.shipped_at is None:
        issue.shipped_at = now
        issue.shipped_by_user_id = current_user.id
    elif new_status == "angekommen" and issue.arrived_at is None:
        issue.arrived_at = now
        issue.arrived_by_user_id = current_user.id
        # Sync mit altem status-Feld: angekommen impliziert done.
        issue.status = "done"

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
