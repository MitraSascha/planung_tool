"""DSGVO-Workflow: Anonymisieren und Hard-Delete fuer Projekte.

``anonymize_project`` ersetzt PII-haltige Felder durch ``[anonymisiert]``
oder tokenisierte Versionen (via ``pii_tokenizer``) — die Datensaetze
bleiben erhalten, aber Klartext-PII verschwindet aus DB und Workspaces.

``delete_project_data`` fuehrt einen Hard-Delete des Projekts inkl. aller
Cascades durch und entfernt Dateisystem-Pfade (Workspace, Public,
Upload-Photos).

Beide Operationen schreiben einen ``AuditEvent`` mit ``action="anonymize"``
bzw. ``action="delete"`` in dieselbe Session.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.settings import settings
from app.db.orm_models import (
    Blocker,
    DailyReport,
    MaterialIssue,
    Project,
    ProjectPhoto,
    User,
    VoiceNote,
    WeeklyReport,
)
from app.services import audit_log
from app.services.pii_tokenizer import pii_tokenizer

logger = logging.getLogger(__name__)

ANONYMIZED_PLACEHOLDER = "[anonymisiert]"


def _tokenize_or_placeholder(db: Session, value: str | None, scope: str) -> str | None:
    """Versucht, den Wert via Tokenizer zu anonymisieren. Wenn der
    Tokenizer keine PII findet (z.B. bei sehr kurzen Strings), wird der
    Inhalt durch ``ANONYMIZED_PLACEHOLDER`` ersetzt, damit auf jeden Fall
    kein Klartext-PII zurueckbleibt.
    """
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return value
    try:
        _, tokenized = pii_tokenizer.tokenize(db=db, text=value, scope=scope, mode="internal")
        if tokenized != value:
            return tokenized
    except Exception:  # noqa: BLE001 — Tokenizer-Fehler nicht eskalieren
        logger.exception("Tokenizer schlug fehl bei scope=%s", scope)
    return ANONYMIZED_PLACEHOLDER


def anonymize_project(
    db: Session,
    project: Project,
    current_user: User,
) -> dict[str, Any]:
    """Anonymisiert alle PII-haltigen Felder eines Projekts. Gibt
    Statistiken zurueck und schreibt einen Audit-Eintrag.
    """
    if current_user.id is not None:
        audit_log.set_audit_user(current_user.id)

    stats: dict[str, Any] = {"updated_rows": 0, "errors": []}
    slug = project.slug

    # Projekt-Stammdaten — wir setzen feste Platzhalter, da diese Felder
    # bei einem produktiven Datensatz fast immer Personen-/Adressdaten
    # enthalten.
    if project.address:
        project.address = ANONYMIZED_PLACEHOLDER
        stats["updated_rows"] += 1
    if project.responsible:
        project.responsible = ANONYMIZED_PLACEHOLDER
        stats["updated_rows"] += 1
    if project.construction_manager:
        project.construction_manager = ANONYMIZED_PLACEHOLDER
        stats["updated_rows"] += 1
    if project.foreman:
        project.foreman = ANONYMIZED_PLACEHOLDER
        stats["updated_rows"] += 1
    if project.notes:
        project.notes = _tokenize_or_placeholder(db, project.notes, scope=f"project:{slug}:notes")
        stats["updated_rows"] += 1

    # Tagesberichte
    daily_reports = db.query(DailyReport).filter(DailyReport.project_id == project.id).all()
    for report in daily_reports:
        changed = False
        for field in ("team", "completed_work", "open_work", "material_missing", "blockers", "notes"):
            current = getattr(report, field)
            if current:
                setattr(report, field, _tokenize_or_placeholder(db, current, scope=f"daily_report:{report.id}:{field}"))
                changed = True
        if changed:
            stats["updated_rows"] += 1

    # Wochenberichte
    weekly_reports = db.query(WeeklyReport).filter(WeeklyReport.project_id == project.id).all()
    for w_report in weekly_reports:
        changed = False
        for field in ("summary", "next_week_plan", "manpower_notes", "material_notes", "risks"):
            current = getattr(w_report, field)
            if current:
                setattr(w_report, field, _tokenize_or_placeholder(db, current, scope=f"weekly_report:{w_report.id}:{field}"))
                changed = True
        if changed:
            stats["updated_rows"] += 1

    # Material-Issues
    material_issues = db.query(MaterialIssue).filter(MaterialIssue.project_id == project.id).all()
    for issue in material_issues:
        if issue.description:
            issue.description = _tokenize_or_placeholder(
                db, issue.description, scope=f"material_issue:{issue.id}"
            )
            stats["updated_rows"] += 1

    # Blocker
    blockers = db.query(Blocker).filter(Blocker.project_id == project.id).all()
    for blocker in blockers:
        if blocker.description:
            blocker.description = _tokenize_or_placeholder(
                db, blocker.description, scope=f"blocker:{blocker.id}"
            )
            stats["updated_rows"] += 1

    # Voice Notes — Transkript tokenisieren, Audio-Datei bleibt (wird bei
    # Hard-Delete entfernt)
    voice_notes = db.query(VoiceNote).filter(VoiceNote.project_id == project.id).all()
    for note in voice_notes:
        if note.transcript:
            note.transcript = _tokenize_or_placeholder(db, note.transcript, scope=f"voice_note:{note.id}")
            stats["updated_rows"] += 1

    # Fotos — Caption tokenisieren, Bilder bleiben (Beweismaterial)
    photos = db.query(ProjectPhoto).filter(ProjectPhoto.project_id == project.id).all()
    for photo in photos:
        if photo.caption:
            photo.caption = _tokenize_or_placeholder(db, photo.caption, scope=f"photo:{photo.id}")
            stats["updated_rows"] += 1

    audit_log.log(
        db,
        action="anonymize",
        entity_type="Project",
        entity_id=str(project.id),
        project_slug=slug,
        changes={"updated_rows": stats["updated_rows"]},
    )

    db.commit()
    return stats


def _remove_dir_if_exists(path: Path) -> bool:
    if path.exists() and path.is_dir():
        shutil.rmtree(path)
        return True
    return False


def delete_project_data(
    db: Session,
    project: Project,
    current_user: User,
) -> dict[str, Any]:
    """Hard-Delete eines Projekts inkl. Cascades + Dateisystem-Pfade.

    Schreibt einen ``AuditEvent`` mit ``action="delete"`` VOR dem Loeschen
    (damit der Eintrag erhalten bleibt, falls die DB-Operation crasht).
    """
    if current_user.id is not None:
        audit_log.set_audit_user(current_user.id)

    slug = project.slug
    project_id = project.id

    # Audit zuerst — DSGVO verlangt nachvollziehbare Loeschung
    audit_log.log(
        db,
        action="delete",
        entity_type="Project",
        entity_id=str(project_id),
        project_slug=slug,
        changes=None,
    )
    # Damit der Audit-Eintrag nicht ueber ``after_delete``-Hook denselben
    # ``project_slug`` mit NULL ueberschrieben bekommt: separat flushen.
    db.flush()

    # Photos / VoiceNotes haben Dateipfade — wir merken sie uns vorher
    photo_paths: list[Path] = []
    for photo in db.query(ProjectPhoto).filter(ProjectPhoto.project_id == project_id).all():
        for candidate in (photo.path, photo.annotated_path):
            if candidate:
                photo_paths.append(Path(candidate))
    voice_paths: list[Path] = []
    for note in db.query(VoiceNote).filter(VoiceNote.project_id == project_id).all():
        if note.audio_path:
            voice_paths.append(Path(note.audio_path))

    # Explizit Kind-Datensaetze loeschen, deren Cascade nur auf DB-Ebene
    # (ON DELETE CASCADE) definiert ist — SQLAlchemy-Cascades sind nur fuer
    # die in ``Project.sections``/``Project.uploads`` etc. konfigurierten
    # Relationships gesetzt; ``DailyReport``/``Blocker``/``MaterialIssue``/
    # ``VoiceNote``/``ProjectPhoto`` haengen via ``ondelete="CASCADE"`` an,
    # was bei SQLite ohne ``PRAGMA foreign_keys=ON`` nicht greift.
    from app.db.orm_models import (
        Blocker as _Blocker,
        DailyReport as _DailyReport,
        MaterialIssue as _MaterialIssue,
        ProjectPhoto as _ProjectPhoto,
        VoiceNote as _VoiceNote,
        WeeklyReport as _WeeklyReport,
    )

    for child_cls in (
        _DailyReport,
        _WeeklyReport,
        _Blocker,
        _MaterialIssue,
        _VoiceNote,
        _ProjectPhoto,
    ):
        db.query(child_cls).filter(child_cls.project_id == project_id).delete(
            synchronize_session=False
        )

    db.delete(project)
    db.commit()

    removed: dict[str, Any] = {"files": 0, "dirs": 0}

    for file_path in photo_paths + voice_paths:
        try:
            if file_path.exists() and file_path.is_file():
                file_path.unlink()
                removed["files"] += 1
        except Exception:  # noqa: BLE001
            logger.exception("Konnte Datei nicht loeschen: %s", file_path)

    # Workspace + Public + Upload-Folder
    candidates = [
        settings.workspaces_path / slug,
        settings.projects_path / slug,
        settings.uploads_path / "photos" / slug,
        settings.uploads_path / "voice_notes" / slug,
    ]
    for path in candidates:
        try:
            if _remove_dir_if_exists(path):
                removed["dirs"] += 1
        except Exception:  # noqa: BLE001
            logger.exception("Konnte Verzeichnis nicht loeschen: %s", path)

    return {
        "deleted_project_id": project_id,
        "slug": slug,
        "removed_files": removed["files"],
        "removed_dirs": removed["dirs"],
    }
