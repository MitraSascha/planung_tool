"""Tests fuer ``app.services.dsgvo_workflow``."""
from __future__ import annotations

from datetime import date

import pytest

from app.core.settings import settings
from app.db.orm_models import (
    AuditEvent,
    Blocker,
    DailyReport,
    MaterialIssue,
    Project,
    User,
    VoiceNote,
)
from app.services import dsgvo_workflow


@pytest.fixture()
def admin_user(db_session) -> User:
    user = User(
        username="dsgvo-admin",
        display_name="DSGVO Admin",
        password_hash="pbkdf2_sha256$x$y",
        global_role="admin",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def populated_project(db_session, admin_user: User) -> Project:
    project = Project(
        slug="anon-proj",
        name="Anonymisierungs-Test",
        address="Musterstr. 12, 10115 Berlin",
        responsible="Max Mustermann",
        construction_manager="Erika Beispiel",
        foreman="Hans Vorarbeiter",
        notes="Kontakt: max@example.com",
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    db_session.add(
        DailyReport(
            project_id=project.id,
            user_id=admin_user.id,
            report_date=date(2024, 5, 1),
            team="Max, Erika",
            completed_work="Heizungsmontage bei Familie Mustermann",
            notes="Telefon: +49 30 1234567",
        )
    )
    db_session.add(
        MaterialIssue(
            project_id=project.id,
            user_id=admin_user.id,
            description="Lieferant Mueller GmbH liefert verspaetet",
        )
    )
    db_session.add(
        Blocker(
            project_id=project.id,
            user_id=admin_user.id,
            description="Termin mit Bauherr Schmidt verschoben",
        )
    )
    db_session.add(
        VoiceNote(
            project_id=project.id,
            user_id=admin_user.id,
            audio_path="/tmp/does-not-exist.wav",
            transcript="Heute war Herr Schulze auf der Baustelle.",
            transcription_status="ok",
        )
    )
    db_session.commit()
    return project


def test_anonymize_project_replaces_pii(db_session, admin_user: User, populated_project: Project) -> None:
    stats = dsgvo_workflow.anonymize_project(db_session, populated_project, admin_user)

    db_session.refresh(populated_project)
    assert populated_project.address == dsgvo_workflow.ANONYMIZED_PLACEHOLDER
    assert populated_project.responsible == dsgvo_workflow.ANONYMIZED_PLACEHOLDER
    assert populated_project.construction_manager == dsgvo_workflow.ANONYMIZED_PLACEHOLDER
    assert populated_project.foreman == dsgvo_workflow.ANONYMIZED_PLACEHOLDER
    assert "max@example.com" not in (populated_project.notes or "")

    daily = db_session.query(DailyReport).filter_by(project_id=populated_project.id).one()
    assert daily.completed_work and "Mustermann" not in daily.completed_work
    assert daily.notes and "1234567" not in daily.notes

    voice = db_session.query(VoiceNote).filter_by(project_id=populated_project.id).one()
    assert voice.transcript and "Schulze" not in voice.transcript

    assert stats["updated_rows"] > 0

    # Audit-Event mit action="anonymize"
    audit_events = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "anonymize", AuditEvent.entity_type == "Project")
        .all()
    )
    assert len(audit_events) >= 1
    assert audit_events[-1].project_slug == "anon-proj"


def test_delete_project_writes_audit_and_removes_files(
    db_session, admin_user: User, populated_project: Project, tmp_path, monkeypatch
) -> None:
    # Storage-Pfade redirecten, damit shutil.rmtree sicher ist
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    (storage_root / "workspaces").mkdir()
    (storage_root / "projects").mkdir()
    (storage_root / "uploads").mkdir()
    monkeypatch.setattr(settings, "storage_root", storage_root)

    workspace_dir = settings.workspaces_path / populated_project.slug
    workspace_dir.mkdir()
    (workspace_dir / "input.json").write_text("{}", encoding="utf-8")

    public_dir = settings.projects_path / populated_project.slug
    public_dir.mkdir()

    project_id = populated_project.id
    slug = populated_project.slug

    result = dsgvo_workflow.delete_project_data(db_session, populated_project, admin_user)

    assert result["deleted_project_id"] == project_id
    assert db_session.query(Project).filter_by(id=project_id).one_or_none() is None
    # Cascades
    assert db_session.query(DailyReport).filter_by(project_id=project_id).count() == 0
    assert db_session.query(MaterialIssue).filter_by(project_id=project_id).count() == 0
    assert db_session.query(Blocker).filter_by(project_id=project_id).count() == 0
    assert db_session.query(VoiceNote).filter_by(project_id=project_id).count() == 0

    # Verzeichnisse entfernt
    assert not workspace_dir.exists()
    assert not public_dir.exists()
    assert result["removed_dirs"] >= 2

    # Audit-Event geschrieben (delete)
    delete_events = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "delete", AuditEvent.entity_type == "Project")
        .all()
    )
    assert any(e.entity_id == str(project_id) and e.project_slug == slug for e in delete_events)
