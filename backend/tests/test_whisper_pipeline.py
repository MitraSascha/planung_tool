"""Tests fuer den ``whisper_pipeline``-Hintergrund-Worker."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from app.db import database as database_module
from app.db.orm_models import Project, VoiceNote
from app.services import whisper_pipeline
from app.services.whisper_provider import TranscriptionResult


class _FakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[Path] = []

    def transcribe(self, audio_path: Path, language_hint: str | None = "de") -> TranscriptionResult:
        self.calls.append(audio_path)
        return TranscriptionResult(
            text=f"Transkript fuer {audio_path.name}",
            language="de",
            provider=self.name,
        )


class _FailingProvider:
    name = "failing"

    def transcribe(self, audio_path: Path, language_hint: str | None = "de") -> TranscriptionResult:
        raise RuntimeError("simulierter Fehler")


@pytest.fixture()
def project_with_voice_note(db_engine, db_session, tmp_path: Path) -> tuple[Project, VoiceNote, Path]:
    # SessionLocal des Pipeline-Codes auf dieselbe In-Memory-DB binden
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    original = database_module.SessionLocal
    database_module.SessionLocal = factory
    try:
        project = Project(slug="alpha", name="Alpha")
        db_session.add(project)
        db_session.flush()

        audio_path = tmp_path / "voice.webm"
        audio_path.write_bytes(b"\x00\x01\x02")

        note = VoiceNote(
            project_id=project.id,
            audio_path=str(audio_path),
            intent="freitext",
            transcription_status="pending",
        )
        db_session.add(note)
        db_session.commit()
        yield project, note, audio_path
    finally:
        database_module.SessionLocal = original


def test_transcribe_in_background_sets_ok(
    project_with_voice_note, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, note, audio_path = project_with_voice_note
    fake = _FakeProvider()

    whisper_pipeline._transcribe_in_background(note.id, provider_factory=lambda: fake)

    # frische Session zum Verifizieren
    with database_module.SessionLocal() as fresh:
        reloaded = fresh.query(VoiceNote).filter(VoiceNote.id == note.id).one()
        assert reloaded.transcription_status == "ok"
        assert reloaded.transcript == f"Transkript fuer {audio_path.name}"
        assert reloaded.transcript_provider == "fake"
        assert reloaded.transcript_language == "de"
        assert reloaded.transcribed_at is not None
        assert reloaded.transcription_error is None
    assert fake.calls == [audio_path]


def test_transcribe_in_background_sets_failed_on_exception(
    project_with_voice_note,
) -> None:
    project, note, audio_path = project_with_voice_note
    whisper_pipeline._transcribe_in_background(
        note.id, provider_factory=lambda: _FailingProvider()
    )

    with database_module.SessionLocal() as fresh:
        reloaded = fresh.query(VoiceNote).filter(VoiceNote.id == note.id).one()
        assert reloaded.transcription_status == "failed"
        assert "simulierter Fehler" in (reloaded.transcription_error or "")
        assert reloaded.transcript is None


def test_transcribe_in_background_fails_for_missing_audio(project_with_voice_note) -> None:
    project, note, audio_path = project_with_voice_note
    audio_path.unlink()
    whisper_pipeline._transcribe_in_background(
        note.id, provider_factory=lambda: _FakeProvider()
    )
    with database_module.SessionLocal() as fresh:
        reloaded = fresh.query(VoiceNote).filter(VoiceNote.id == note.id).one()
        assert reloaded.transcription_status == "failed"
        assert "Audio-Datei nicht gefunden" in (reloaded.transcription_error or "")


def test_register_listeners_skipped_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.settings import settings as live_settings

    whisper_pipeline.unregister_listeners()
    monkeypatch.setattr(live_settings, "disable_whisper_hook", True)
    whisper_pipeline.register_listeners()
    # nach Aufruf bleibt das Flag gesetzt, aber kein echter Listener auf VoiceNote
    from sqlalchemy import event

    assert not event.contains(VoiceNote, "after_insert", whisper_pipeline._after_insert_listener)
    whisper_pipeline.unregister_listeners()
