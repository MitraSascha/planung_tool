"""Tests fuer das Audit-Log (Phase 16).

Decken Listener-Registration, ``disable_audit_hook``-Schalter sowie das
Diff-Format fuer Updates ab.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.core.settings import settings
from app.db.orm_models import AuditEvent, DailyReport, Project, User
from app.services import audit_log


@pytest.fixture()
def audit_hook(db_session, monkeypatch):
    """Aktiviere Audit-Listener fuer diese Test-Session."""
    monkeypatch.setattr(settings, "disable_audit_hook", False)
    audit_log.unregister_listeners()
    audit_log._listeners_registered = False
    audit_log.register_listeners()
    yield
    audit_log.unregister_listeners()


@pytest.fixture()
def user_row(db_session) -> User:
    user = User(
        username="auditor",
        display_name="Auditor",
        password_hash="pbkdf2_sha256$x$y",
        global_role="admin",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def project_row(db_session) -> Project:
    project = Project(slug="aud-proj", name="Audit Projekt")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


def test_listener_registers_create_event_for_daily_report(
    db_session, audit_hook, user_row: User, project_row: Project
) -> None:
    report = DailyReport(
        project_id=project_row.id,
        user_id=user_row.id,
        report_date=date(2024, 5, 1),
        completed_work="Heizungsmontage",
    )
    db_session.add(report)
    db_session.commit()

    events = db_session.query(AuditEvent).filter(AuditEvent.entity_type == "DailyReport").all()
    assert len(events) == 1
    assert events[0].action == "create"
    assert events[0].entity_id == str(report.id)
    assert events[0].project_slug == project_row.slug


def test_listener_records_update_with_column_diff(
    db_session, audit_hook, user_row: User, project_row: Project
) -> None:
    report = DailyReport(
        project_id=project_row.id,
        user_id=user_row.id,
        report_date=date(2024, 5, 2),
        completed_work="A",
    )
    db_session.add(report)
    db_session.commit()

    report.completed_work = "Updated"
    report.notes = "Some note"
    db_session.commit()

    update_events = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.entity_type == "DailyReport", AuditEvent.action == "update")
        .all()
    )
    assert len(update_events) == 1
    assert update_events[0].changes_json is not None
    assert "completed_work" in update_events[0].changes_json
    assert "notes" in update_events[0].changes_json
    # Werte duerfen NICHT geloggt werden (DSGVO)
    assert "Updated" not in update_events[0].changes_json
    assert "Some note" not in update_events[0].changes_json


def test_listener_records_delete(
    db_session, audit_hook, user_row: User, project_row: Project
) -> None:
    report = DailyReport(
        project_id=project_row.id,
        user_id=user_row.id,
        report_date=date(2024, 5, 3),
    )
    db_session.add(report)
    db_session.commit()
    report_id = report.id

    db_session.delete(report)
    db_session.commit()

    delete_events = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.entity_type == "DailyReport", AuditEvent.action == "delete")
        .all()
    )
    assert len(delete_events) == 1
    assert delete_events[0].entity_id == str(report_id)


def test_disable_audit_hook_skips_events(
    db_session, user_row: User, project_row: Project, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "disable_audit_hook", True)
    audit_log.unregister_listeners()
    audit_log._listeners_registered = False
    audit_log.register_listeners()

    report = DailyReport(
        project_id=project_row.id,
        user_id=user_row.id,
        report_date=date(2024, 5, 4),
    )
    db_session.add(report)
    db_session.commit()

    events = db_session.query(AuditEvent).all()
    # Nur die fixture-events (es duerfte keine fuer DailyReport geben)
    daily_events = [e for e in events if e.entity_type == "DailyReport"]
    assert daily_events == []
    audit_log.unregister_listeners()


def test_log_helper_uses_request_context(db_session, user_row: User) -> None:
    """``audit_log.log()`` muss user_id/ip/user_agent aus den ContextVars
    aufnehmen."""
    token_user = audit_log.audit_user_id.set(user_row.id)
    token_ip = audit_log.audit_ip.set("10.0.0.1")
    token_ua = audit_log.audit_user_agent.set("pytest-agent/1.0")
    try:
        audit_log.log(
            db_session,
            action="anonymize",
            entity_type="Project",
            entity_id="42",
            project_slug="some-slug",
            changes={"updated_rows": 3},
        )
        db_session.commit()
    finally:
        audit_log.audit_user_agent.reset(token_ua)
        audit_log.audit_ip.reset(token_ip)
        audit_log.audit_user_id.reset(token_user)

    event_row = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "anonymize")
        .one()
    )
    assert event_row.user_id == user_row.id
    assert event_row.ip_address == "10.0.0.1"
    assert event_row.user_agent == "pytest-agent/1.0"
    assert event_row.project_slug == "some-slug"
    assert event_row.changes_json is not None and "updated_rows" in event_row.changes_json
