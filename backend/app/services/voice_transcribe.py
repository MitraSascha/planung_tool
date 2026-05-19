"""Inline Push-to-Talk Transkription mit Auto-Sprach-Detect + Übersetzung nach Deutsch.

Unterschied zur ``whisper_pipeline`` (die hängt am ``VoiceNote``-Insert): hier
gibt es **keine Persistenz** — Audio kommt rein, Text-Deutsch kommt direkt
zurück. Der Caller (Frontend) fügt den Text ins Eingabefeld ein.

Pipeline:

1. Whisper transcribe **ohne** ``language``-Hint → Auto-Detect.
2. Wenn erkannte Sprache != ``de`` → kurzer LLM-Call (gpt-4o-mini, schnell und
   günstig) übersetzt nach Deutsch und bewahrt SHK-Fachvokabular.
3. Response: ``{ text_de, original_text, language, translated, provider }``.

Bei fehlendem Key (``OPENAI_API_KEY``) wirft die Funktion ``RuntimeError`` —
der Endpoint liefert 503, das Frontend fällt dann auf Browser-SpeechRecognition
zurück.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.core.settings import settings
from app.services.whisper_provider import (
    OpenAIWhisperApiProvider,
    TranscriptionResult,
    WhisperProvider,
    get_whisper_provider,
)

logger = logging.getLogger(__name__)

# Modell für die Mini-Übersetzungs-Aufgabe. gpt-4o-mini ist schnell (~500ms),
# billig und für kurze Übersetzungen mehr als ausreichend.
TRANSLATION_MODEL = "gpt-4o-mini"


@dataclass
class VoiceTranscribeResult:
    text_de: str
    original_text: str
    language: str | None
    translated: bool
    provider: str


def _autodetect_provider() -> WhisperProvider:
    """Provider-Auswahl für Inline-PTT.

    Wir können nicht stumpf ``get_whisper_provider()`` nehmen, weil der
    Default-Provider ``openai`` eine Fallback-Kette OpenAI→Codex baut. Codex
    transkribiert aber nur mit hartem deutschem Prompt — kein Auto-Detect.
    Für Inline-PTT mit Mehrsprachigkeit greifen wir direkt OpenAI Whisper.

    Wenn kein API-Key gesetzt ist, wirft ``OpenAIWhisperApiProvider.transcribe``
    einen ``RuntimeError`` — den fängt der Endpoint und liefert 503.
    """
    return OpenAIWhisperApiProvider()


def _needs_translation(language: str | None, target: str) -> bool:
    if not language:
        return False
    return language.strip().lower() != target.strip().lower()


def _translate_to_german(text: str, source_language: str | None) -> str:
    """Übersetzung via OpenAI Chat-Completion. Bei Fehler wird der Originaltext
    zurückgegeben — die Transkription soll nicht wegen einer LLM-Panne komplett
    scheitern. Der Caller sieht ``translated=False`` und kann reagieren.
    """
    api_key = settings.openai_api_key
    if not api_key:
        logger.warning("Übersetzungs-Schritt übersprungen: OPENAI_API_KEY fehlt")
        return text
    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        logger.warning("openai-Package fehlt — Übersetzung übersprungen")
        return text

    client = OpenAI(api_key=api_key)
    src = (source_language or "unbekannte Sprache").lower()
    system = (
        "Du bist ein Übersetzer für SHK-Handwerk (Sanitär, Heizung, Klima). "
        "Übersetze den Eingabetext nach Deutsch und behalte Fachbegriffe "
        "(z.B. Vorlauf/Rücklauf, Druckprüfung, Strang, Heizkreis, "
        "Inbetriebnahme) korrekt im Deutschen bei. Wenn der Text bereits "
        "Deutsch ist, gib ihn unverändert zurück. Antworte AUSSCHLIESSLICH "
        "mit dem übersetzten Text — keine Einleitung, keine Anführungszeichen."
    )
    user = f"Quellsprache: {src}\nText:\n{text}"
    try:
        completion = client.chat.completions.create(
            model=TRANSLATION_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            timeout=15.0,
        )
        translated = (completion.choices[0].message.content or "").strip()
        if not translated:
            logger.warning("LLM-Übersetzung lieferte leeren Text — Original zurück")
            return text
        return translated
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM-Übersetzung fehlgeschlagen, gebe Original zurück: %s", exc)
        return text


def transcribe_and_translate(
    audio_path: Path,
    target_language: str = "de",
) -> VoiceTranscribeResult:
    """Transkribiere Audio + wenn nötig in Zielsprache übersetzen.

    Args:
        audio_path: Pfad zum Audio-File (jedes Format das Whisper unterstützt).
        target_language: ISO-Code der Zielsprache. Default ``de`` — wenn das
            Transkript bereits in der Zielsprache ist, läuft kein Übersetzungs-Hop.

    Returns:
        :class:`VoiceTranscribeResult`. Bei Whisper-Fehler wird ``RuntimeError``
        weitergereicht — der Endpoint mappt das auf 5xx.
    """
    provider = _autodetect_provider()
    # language_hint=None ⇒ Whisper Auto-Detect (s. Provider-Erweiterung).
    raw: TranscriptionResult = provider.transcribe(audio_path, language_hint=None)

    original_text = raw.text or ""
    detected = (raw.language or "").lower() or None

    if not original_text.strip():
        return VoiceTranscribeResult(
            text_de="",
            original_text="",
            language=detected,
            translated=False,
            provider=raw.provider,
        )

    if _needs_translation(detected, target_language):
        translated_text = _translate_to_german(original_text, detected)
        actually_translated = translated_text.strip() != original_text.strip()
        return VoiceTranscribeResult(
            text_de=translated_text,
            original_text=original_text,
            language=detected,
            translated=actually_translated,
            provider=raw.provider,
        )

    return VoiceTranscribeResult(
        text_de=original_text,
        original_text=original_text,
        language=detected,
        translated=False,
        provider=raw.provider,
    )
