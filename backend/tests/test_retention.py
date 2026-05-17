"""Tests fuer ``app.services.retention``."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.db.orm_models import (
    AuditEvent,
    Blocker,
    DailyReport,
    DataRetentionRule,
    Project,
    User,
)
from app.services import retention


@pytest.fixture()
def user_row(db_session) -> User:
    user = User(
        username="ret-user",
        display_name="Retention",
        password_hash="pbkdf2_sha256$x$y",
        global_role="admin",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def project_row(db_session) -> Project:
    project = Project(slug="ret-proj", name="Retention Projekt")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


def _old(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def test_upsert_creates_and_updates_rule(db_session) -> None:
    rule = retention.upsert_retention_rule(
        db_session,
        {"entity_type": "DailyReport", "ttl_days": 30, "action": "delete", "enabled": True},
    )
    assert rule.id is not None and rule.ttl_days == 30

    updated = retention.upsert_retention_rule(
        db_session,
        {"entity_type": "DailyReport", "ttl_days": 90, "action": "anonymize"},
    )
    assert updated.id == rule.id
    assert updated.ttl_days == 90
    assert updated.action == "anonymize"


def test_upsert_rejects_unknown_entity(db_session) -> None:
    with pytest.raises(ValueError):
        retention.upsert_retention_rule(
            db_session,
            {"entity_type": "Nonexistent", "ttl_days": 1},
        )


def test_cleanup_deletes_old_daily_reports(
    db_session, user_row: User, project_row: Project
) -> None:
    old_report = DailyReport(
        project_id=project_row.id,
        user_id=user_row.id,
        report_date=date(2020, 1, 1),
        completed_work="Alt",
    )
    new_report = DailyReport(
        project_id=project_row.id,
        user_id=user_row.id,
        report_date=date.today(),
        completed_work="Neu",
    )
    db_session.add_all([old_report, new_report])
    db_session.commit()

    # ``created_at`` rueckdatieren
    old_report.created_at = _old(180)
    db_session.commit()

    retention.upsert_retention_rule(
        db_session,
        {"entity_type": "DailyReport", "ttl_days": 30, "action": "delete"},
    )

    result = retention.run_retention_cleanup(db_session, dry_run=False)
    assert result["dry_run"] is False
    daily_stats = result["rules"]["DailyReport"]
    assert daily_stats["affected"] == 1
    assert daily_stats["executed"] == 1

    remaining = db_session.query(DailyReport).all()
    assert len(remaining) == 1
    assert remaining[0].id == new_report.id

    # Audit-Eintrag fuer Cleanup
    audit_rows = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.entity_type == "DailyReport", AuditEvent.action == "delete")
        .all()
    )
    assert any(
        row.changes_json and "cleanup" in row.changes_json for row in audit_rows
    )


def test_cleanup_dry_run_changes_nothing(
    db_session, user_row: User, project_row: Project
) -> None:
    report = DailyReport(
        project_id=project_row.id,
        user_id=user_row.id,
        report_date=date(2020, 1, 1),
    )
    db_session.add(report)
    db_session.commit()
    report.created_at = _old(365)
    db_session.commit()

    retention.upsert_retention_rule(
        db_session,
        {"entity_type": "DailyReport", "ttl_days": 30, "action": "delete"},
    )

    result = retention.run_retention_cleanup(db_session, dry_run=True)
    assert result["dry_run"] is True
    assert result["rules"]["DailyReport"]["affected"] == 1
    assert result["rules"]["DailyReport"]["executed"] == 0

    # Datensatz noch da
    assert db_session.query(DailyReport).count() == 1


def test_cleanup_skips_disabled_rule(
    db_session, user_row: User, project_row: Project
) -> None:
    blocker = Blocker(
        project_id=project_row.id,
        user_id=user_row.id,
        description="Alter Blocker",
    )
    db_session.add(blocker)
    db_session.commit()
    blocker.created_at = _old(500)
    db_session.commit()

    rule = retention.upsert_retention_rule(
        db_session,
        {"entity_type": "Blocker", "ttl_days": 30, "action": "delete", "enabled": False},
    )
    assert rule.enabled is False

    result = retention.run_retention_cleanup(db_session, dry_run=False)
    # Disabled rule liefert keine Stats
    assert "Blocker" not in result["rules"]
    assert db_session.query(Blocker).count() == 1


def test_cleanup_anonymizes_when_action_anonymize(
    db_session, user_row: User, project_row: Project
) -> None:
    report = DailyReport(
        project_id=project_row.id,
        user_id=user_row.id,
        report_date=date(2020, 1, 1),
        completed_work="Bei Max Mustermann gearbeitet",
        notes="Telefon: +49 30 1234567",
    )
    db_session.add(report)
    db_session.commit()
    report.created_at = _old(180)
    db_session.commit()

    retention.upsert_retention_rule(
        db_session,
        {"entity_type": "DailyReport", "ttl_days": 30, "action": "anonymize"},
    )

    result = retention.run_retention_cleanup(db_session, dry_run=False)
    assert result["rules"]["DailyReport"]["executed"] >= 1

    db_session.refresh(report)
    assert report.completed_work and "Mustermann" not in report.completed_work
    assert report.notes and "1234567" not in report.notes
