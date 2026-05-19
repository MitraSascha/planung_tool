"""Inline Push-to-Talk Endpoint.

Frontend nimmt Audio auf, schickt es als multipart an
``POST /api/voice/transcribe``. Backend transkribiert mit Auto-Sprach-Detect
und übersetzt nach Deutsch wenn nötig (siehe ``services/voice_transcribe.py``).

Bei fehlender OpenAI-Konfiguration (``OPENAI_API_KEY`` leer) wird 503
zurückgegeben — das Frontend fällt dann auf die Browser-eigene
``SpeechRecognition``-API zurück.
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.settings import settings
from app.db.orm_models import User
from app.services.auth import get_current_user
from app.services.voice_transcribe import (
    VoiceTranscribeResult,
    transcribe_and_translate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


ALLOWED_AUDIO_EXTENSIONS = {".webm", ".mp3", ".m4a", ".wav", ".ogg", ".opus"}
# Hard cap so der Endpoint nicht aus Versehen 100MB-Files frisst — Push-to-Talk-
# Aufnahmen sind in der Praxis < 1MB für 30s Audio.
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MiB — entspricht dem OpenAI-Whisper-Limit


class VoiceTranscribeResponse(BaseModel):
    """Antwort auf ``POST /api/voice/transcribe``.

    Frontend nutzt typischerweise nur ``text_de`` (das ist der Text, der ins
    Eingabefeld geschrieben wird). ``original_text``/``language``/``translated``
    sind nützlich für Audit + UI-Hinweise (z.B. „🌐 aus dem Türkischen
    übersetzt").
    """

    text_de: str
    original_text: str
    language: str | None
    translated: bool
    provider: str


def _suffix_for(filename: str | None, content_type: str | None) -> str:
    """Suffix robust ableiten — Browser schicken oft nur ``audio/webm`` ohne
    Dateiname, manche schicken einen generischen ``blob``-Namen ohne Endung.
    Whisper braucht aber eine erkennbare Endung, sonst lehnt das SDK ab.
    """
    if filename:
        suffix = Path(filename).suffix.lower()
        if suffix in ALLOWED_AUDIO_EXTENSIONS:
            return suffix
    if content_type:
        # mime → suffix lookup für die gängigen Browser-MIME-Typen
        mapping = {
            "audio/webm": ".webm",
            "audio/ogg": ".ogg",
            "audio/mp3": ".mp3",
            "audio/mpeg": ".mp3",
            "audio/mp4": ".m4a",
            "audio/x-m4a": ".m4a",
            "audio/wav": ".wav",
            "audio/wave": ".wav",
            "audio/x-wav": ".wav",
            "audio/opus": ".opus",
        }
        base = content_type.split(";", 1)[0].strip().lower()
        if base in mapping:
            return mapping[base]
    # Fallback — Browser liefert manchmal ``audio/webm;codecs=opus``.
    return ".webm"


@router.post("/transcribe", response_model=VoiceTranscribeResponse)
async def transcribe_voice(
    file: UploadFile = File(...),
    target_language: str = Form("de"),
    current_user: User = Depends(get_current_user),
) -> VoiceTranscribeResponse:
    """Push-to-Talk: Audio rein, deutscher Text raus.

    Authentifizierter Endpoint (jeder eingeloggte User). Kein Projekt-Kontext —
    der PTT-Button soll überall funktionieren, auch außerhalb von Projekt-Views.
    """
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "OPENAI_API_KEY ist nicht konfiguriert. "
                "Frontend sollte auf Browser-SpeechRecognition-Fallback wechseln."
            ),
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Leerer Audio-Upload")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Audio zu groß ({len(data)} Bytes, max {MAX_AUDIO_BYTES}).",
        )

    suffix = _suffix_for(file.filename, file.content_type)

    # Temp-File: Whisper-SDK braucht ein File-Handle, einen In-Memory-Bytes-Wrapper
    # akzeptiert es zwar auch, aber das ``faster-whisper``-Backend (lokaler
    # Fallback) braucht einen Pfad. Tempfile ist der gemeinsame Nenner.
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(data)
    try:
        result: VoiceTranscribeResult = transcribe_and_translate(
            tmp_path, target_language=target_language
        )
    except RuntimeError as exc:
        logger.warning("Whisper-Transkription scheiterte: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass

    return VoiceTranscribeResponse(
        text_de=result.text_de,
        original_text=result.original_text,
        language=result.language,
        translated=result.translated,
        provider=result.provider,
    )


@router.get("/availability")
def voice_availability(
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    """Frontend kann damit prüfen ob Server-PTT verfügbar ist (Key gesetzt).
    Wenn nicht, wird direkt der Browser-Fallback aktiviert ohne erst einen
    fehlgeschlagenen POST zu probieren.
    """
    return {"available": bool(settings.openai_api_key)}
