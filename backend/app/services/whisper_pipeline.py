"""Hintergrund-Transkription fuer ``VoiceNote``-Inserts.

Diese Pipeline reagiert ueber einen SQLAlchemy-``after_insert``-Event-Listener
auf jeden neuen ``VoiceNote``-Datensatz und stoesst einen Daemon-Thread an,
der den konfigurierten Whisper-Provider gegen die Audio-Datei laeuft. Das
Ergebnis wird in einer neuen DB-Session zurueckgeschrieben (`transcript`,
`transcript_provider`, `transcript_language`, `transcription_status`,
`transcribed_at`); Fehler landen als `transcription_error` mit Status
``failed``.

Der Hook ist optional: ``register_listeners()`` ist idempotent und wird einmal
beim FastAPI-Startup aufgerufen. Tests setzen ``settings.disable_whisper_hook``
auf ``True`` oder die Env-Var ``DISABLE_WHISPER_HOOK=1``, damit keine
Background-Threads waehrend der Test-Suite mitlaufen.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import event

from app.core.settings import settings
from app.db import database as _database
from app.db.orm_models import VoiceNote
from app.services.whisper_provider import (
    TranscriptionResult,
    WhisperProvider,
    get_whisper_provider,
)

logger = logging.getLogger(__name__)

_listener_registered = False


def _hook_disabled() -> bool:
    if getattr(settings, "disable_whisper_hook", False):
        return True
    return os.environ.get("DISABLE_WHISPER_HOOK", "") == "1"


def _transcribe_in_background(
    voice_note_id: int,
    provider_factory: Any = get_whisper_provider,
) -> None:
    """Worker-Loop: laedt die VoiceNote frisch, ruft den Provider, schreibt zurueck."""
    with _database.SessionLocal() as db:
        note = db.query(VoiceNote).filter(VoiceNote.id == voice_note_id).one_or_none()
        if note is None:
            logger.warning("VoiceNote %s verschwunden, ueberspringe Transkription", voice_note_id)
            return

        audio_path = Path(note.audio_path)
        if not audio_path.exists():
            note.transcription_status = "failed"
            note.transcription_error = f"Audio-Datei nicht gefunden: {audio_path}"
            db.commit()
            return

        try:
            provider: WhisperProvider = provider_factory()
            result: TranscriptionResult = provider.transcribe(audio_path, language_hint="de")
            note.transcript = result.text
            note.transcript_provider = result.provider
            note.transcript_language = result.language
            note.transcription_status = "ok"
            note.transcription_error = None
            note.transcribed_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as exc:  # noqa: BLE001 — wir wollen jeden Fehler einfangen
            logger.exception("Transkription fehlgeschlagen fuer VoiceNote %s", voice_note_id)
            try:
                # frischer Datensatz, falls die Session inkonsistent ist
                db.rollback()
                note = (
                    db.query(VoiceNote)
                    .filter(VoiceNote.id == voice_note_id)
                    .one_or_none()
                )
                if note is not None:
                    note.transcription_status = "failed"
                    note.transcription_error = str(exc)
                    db.commit()
            except Exception:  # noqa: BLE001 — Fallback nicht kritisch
                logger.exception(
                    "Konnte transcription_status=failed fuer VoiceNote %s nicht setzen",
                    voice_note_id,
                )


def _spawn_worker(voice_note_id: int) -> None:
    thread = threading.Thread(
        target=_transcribe_in_background,
        args=(voice_note_id,),
        name=f"whisper-{voice_note_id}",
        daemon=True,
    )
    thread.start()


def _after_insert_listener(mapper: Any, connection: Any, target: VoiceNote) -> None:
    """SQLAlchemy-Hook: nach jedem VoiceNote-Insert Worker-Thread starten.

    Wir verwenden ``after_insert``, NICHT ``after_flush``, weil wir hier den
    `target.id` brauchen — der ist erst nach dem Insert garantiert verfuegbar.
    Der Thread oeffnet seine eigene Session, das aktuelle ``connection`` /
    ``session`` wird nicht verwendet.
    """
    if _hook_disabled():
        return

    try:
        note_id = int(target.id) if target.id is not None else None
    except (TypeError, ValueError):
        note_id = None
    if note_id is None:
        return
    _spawn_worker(note_id)


def register_listeners() -> None:
    """Registriere Whisper-Hooks. Idempotent — mehrfacher Aufruf ist sicher."""
    global _listener_registered
    if _listener_registered:
        return
    if _hook_disabled():
        logger.info("Whisper-Hook deaktiviert (disable_whisper_hook=True)")
        _listener_registered = True
        return

    event.listen(VoiceNote, "after_insert", _after_insert_listener)
    _listener_registered = True
    logger.info(
        "Whisper-Hook registriert: provider=%s, model=%s",
        settings.whisper_provider,
        settings.whisper_model,
    )


def unregister_listeners() -> None:
    """Nuetzlich fuer Tests, die den Hook gezielt aus- und wieder einschalten."""
    global _listener_registered
    if not _listener_registered:
        return
    try:
        event.remove(VoiceNote, "after_insert", _after_insert_listener)
    except Exception:  # noqa: BLE001 — Listener war nie aktiv
        pass
    _listener_registered = False
