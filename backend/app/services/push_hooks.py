"""SQLAlchemy-Event-Listener fuer automatische Push-Benachrichtigungen.

Analog zu ``whisper_pipeline.register_listeners()`` wird das Setup
einmal beim FastAPI-Startup aufgerufen und ist idempotent.

Triggers:
- Neuer ``Blocker`` mit ``severity in {"high", "critical"}`` → Push an
  Projektmitglieder mit Rolle bauleitung/projektleitung/admin (+ globale
  admins/projektleitungen).
- Neuer ``DailyReport`` mit ``status="red"`` → Push an Bauleitung+PL.
- Drei oder mehr ``DailyReport`` mit Status ``red`` innerhalb der letzten
  7 Tage im selben Projekt → zusaetzlicher Haeufungs-Push.

Der Versand laeuft in einem Daemon-Thread mit eigener DB-Session, damit
die Transaktion des Triggers nicht blockiert wird. Tests deaktivieren
den Hook ueber ``settings.disable_push_hook=True``.
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import event

from app.core.settings import settings
from app.db import database as _database
from app.db.orm_models import (
    Blocker,
    DailyReport,
    MaterialIssue,
    Project,
    ProjectMember,
    User,
)
from app.services import push_messages, push_service

logger = logging.getLogger(__name__)

_listener_registered = False

# Welche Projektrollen / globalen Rollen sollen die Push erhalten?
_LEAD_PROJECT_ROLES = frozenset({"bauleitung", "projektleitung"})
_LEAD_GLOBAL_ROLES = frozenset({"admin", "projektleitung"})

_RED_WINDOW_DAYS = 7
_RED_REPEAT_THRESHOLD = 3


def _hook_disabled() -> bool:
    if getattr(settings, "disable_push_hook", False):
        return True
    return os.environ.get("DISABLE_PUSH_HOOK", "") == "1"


def _collect_lead_user_ids(db: Any, project_id: int) -> list[int]:
    """User-IDs aller Bauleiter/Projektleiter/Admins fuer das Projekt.

    Vereinigung aus
      - ``ProjectMember`` mit project_role in {bauleitung, projektleitung}
      - allen aktiven ``User`` mit global_role in {admin, projektleitung}.
    """
    member_rows = (
        db.query(ProjectMember.user_id)
        .filter(
            ProjectMember.project_id == project_id,
            ProjectMember.project_role.in_(_LEAD_PROJECT_ROLES),
        )
        .all()
    )
    user_ids: set[int] = {row[0] for row in member_rows}

    global_rows = (
        db.query(User.id)
        .filter(
            User.active.is_(True),
            User.global_role.in_(_LEAD_GLOBAL_ROLES),
        )
        .all()
    )
    user_ids.update(row[0] for row in global_rows)
    return sorted(user_ids)


def _handle_blocker_async(blocker_id: int) -> None:
    """Worker: prueft Severity und versendet ggf. Push."""
    with _database.SessionLocal() as db:
        blocker = db.query(Blocker).filter(Blocker.id == blocker_id).one_or_none()
        if blocker is None:
            return
        if blocker.severity not in {"high", "critical"}:
            return
        project = db.query(Project).filter(Project.id == blocker.project_id).one_or_none()
        if project is None:
            return
        user_ids = _collect_lead_user_ids(db, project.id)
        if not user_ids:
            return
        title, body = push_messages.blocker_message(blocker, project)
        push_service.send_push_notification(
            db,
            user_ids,
            title,
            body,
            url=f"/projects/{project.slug}/open-points",
            tag=f"blocker-{project.slug}",
        )


def _handle_daily_report_async(report_id: int) -> None:
    """Worker: prueft Status und versendet ggf. Push (inkl. Haeufung)."""
    with _database.SessionLocal() as db:
        report = db.query(DailyReport).filter(DailyReport.id == report_id).one_or_none()
        if report is None:
            return
        if report.status != "red":
            return
        project = db.query(Project).filter(Project.id == report.project_id).one_or_none()
        if project is None:
            return
        user_ids = _collect_lead_user_ids(db, project.id)
        if not user_ids:
            return

        title, body = push_messages.daily_report_red_message(report, project)
        push_service.send_push_notification(
            db,
            user_ids,
            title,
            body,
            url=f"/projects/{project.slug}/reports",
            tag=f"daily-red-{project.slug}",
        )

        # Haeufungs-Check: 3+ rote Reports in den letzten 7 Tagen.
        window_start = datetime.now(timezone.utc) - timedelta(days=_RED_WINDOW_DAYS)
        red_count = (
            db.query(DailyReport)
            .filter(
                DailyReport.project_id == project.id,
                DailyReport.status == "red",
                DailyReport.created_at >= window_start,
            )
            .count()
        )
        if red_count >= _RED_REPEAT_THRESHOLD:
            rep_title, rep_body = push_messages.repeated_red_message(project, red_count)
            push_service.send_push_notification(
                db,
                user_ids,
                rep_title,
                rep_body,
                url=f"/projects/{project.slug}/reports",
                tag=f"daily-red-cluster-{project.slug}",
            )


def _handle_material_issue_async(issue_id: int) -> None:
    """Worker: bei jeder neuen Materialmeldung Push an Lead-Rollen."""
    with _database.SessionLocal() as db:
        issue = (
            db.query(MaterialIssue).filter(MaterialIssue.id == issue_id).one_or_none()
        )
        if issue is None:
            return
        # Nur push bei wirklich neuer Meldung. Items, die aus dem Daily-Report
        # Auto-Sync stammen, sind ohnehin neu — kein zusätzlicher Filter nötig.
        if issue.procurement_status and issue.procurement_status != "offen":
            return
        project = (
            db.query(Project).filter(Project.id == issue.project_id).one_or_none()
        )
        if project is None:
            return
        user_ids = _collect_lead_user_ids(db, project.id)
        if not user_ids:
            return
        title, body = push_messages.material_issue_message(issue, project)
        push_service.send_push_notification(
            db,
            user_ids,
            title,
            body,
            url=f"/material-issues",
            tag=f"material-issue-{project.slug}-{issue_id}",
        )


def _spawn(target: Any, *args: Any) -> None:
    thread = threading.Thread(target=target, args=args, daemon=True)
    thread.start()


def _blocker_after_insert(mapper: Any, connection: Any, target: Blocker) -> None:
    if _hook_disabled():
        return
    blocker_id = getattr(target, "id", None)
    if not blocker_id:
        return
    _spawn(_handle_blocker_async, int(blocker_id))


def _daily_report_after_insert(mapper: Any, connection: Any, target: DailyReport) -> None:
    if _hook_disabled():
        return
    report_id = getattr(target, "id", None)
    if not report_id:
        return
    _spawn(_handle_daily_report_async, int(report_id))


def _material_issue_after_insert(mapper: Any, connection: Any, target: MaterialIssue) -> None:
    if _hook_disabled():
        return
    issue_id = getattr(target, "id", None)
    if not issue_id:
        return
    _spawn(_handle_material_issue_async, int(issue_id))


def register_listeners() -> None:
    """Registriere Push-Hooks. Idempotent — mehrfacher Aufruf ist sicher."""
    global _listener_registered
    if _listener_registered:
        return
    if _hook_disabled():
        logger.info("Push-Hook deaktiviert (disable_push_hook=True)")
        _listener_registered = True
        return

    event.listen(Blocker, "after_insert", _blocker_after_insert)
    event.listen(DailyReport, "after_insert", _daily_report_after_insert)
    event.listen(MaterialIssue, "after_insert", _material_issue_after_insert)
    _listener_registered = True
    logger.info(
        "Push-Hook registriert: vapid_configured=%s",
        bool(settings.vapid_public_key),
    )


def unregister_listeners() -> None:
    """Helper fuer Tests."""
    global _listener_registered
    if not _listener_registered:
        return
    for model, listener in (
        (Blocker, _blocker_after_insert),
        (DailyReport, _daily_report_after_insert),
        (MaterialIssue, _material_issue_after_insert),
    ):
        try:
            event.remove(model, "after_insert", listener)
        except Exception:  # noqa: BLE001
            pass
    _listener_registered = False
