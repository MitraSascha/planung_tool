"""Whisper-Provider-Strategy fuer Sprachnotiz-Transkription.

Der HEZ-Tool-Stack laeuft entweder mit faster-whisper lokal (Standard, CPU/GPU
auf dem Host), mit der OpenAI-Whisper-API oder mit Codex CLI (audio-faehiges
Modell). Externe Bibliotheken werden lazy importiert, damit eine fehlende
Optional-Dependency nicht beim Modul-Laden crasht.

Die Auswahl steuert ``settings.whisper_provider``:
- "local"           -> :class:`LocalFasterWhisperProvider`
- "openai"          -> OpenAI (mit Codex-Fallback bei Fehlern, sofern Codex authentifiziert)
- "openai_only"     -> nur :class:`OpenAIWhisperApiProvider`, kein Fallback
- "codex"           -> nur :class:`CodexAudioProvider`
- "chain"           -> Kette aus ``settings.whisper_chain`` (kommaseparierte Liste)
- "off"             -> :class:`NullProvider`
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.settings import settings


logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    """Ergebnis eines Whisper-Laufs."""

    text: str
    language: str | None
    provider: str


class WhisperProvider(ABC):
    """Gemeinsame Strategy-Schnittstelle fuer alle Whisper-Implementierungen."""

    name: str = "abstract"

    @abstractmethod
    def transcribe(
        self,
        audio_path: Path,
        language_hint: str | None = "de",
    ) -> TranscriptionResult:
        """Transkribiere die Audio-Datei. Wirft ``RuntimeError`` bei Fehlern."""


class NullProvider(WhisperProvider):
    """Fallback wenn kein Provider konfiguriert ist.

    Wir wollen die Sprachnotiz trotzdem persistieren, aber den Aufrufer klar
    informieren, dass keine Transkription stattgefunden hat. Der
    ``whisper_pipeline``-Listener faengt den Fehler und setzt
    ``transcription_status="failed"`` plus ``transcription_error``.
    """

    name = "null"

    def transcribe(
        self,
        audio_path: Path,
        language_hint: str | None = "de",
    ) -> TranscriptionResult:
        raise RuntimeError(
            "Kein Whisper-Provider konfiguriert. Setze WHISPER_PROVIDER=local "
            "oder WHISPER_PROVIDER=openai in der Umgebung."
        )


class LocalFasterWhisperProvider(WhisperProvider):
    """Lokale Transkription via ``faster-whisper`` (CTranslate2-Backend).

    Das Modell wird beim ersten ``transcribe``-Aufruf lazy geladen und im
    Provider-Instance-State zwischengespeichert, damit Folgeaufrufe den
    Modell-Initialisierungs-Overhead nicht erneut bezahlen.
    """

    name = "local-faster-whisper"

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or settings.whisper_model
        self._model: Any | None = None

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError as exc:  # pragma: no cover — bibliotheksabhaengig
            raise RuntimeError(
                "faster-whisper ist nicht installiert. Installiere `faster-whisper` "
                "oder setze WHISPER_PROVIDER=openai/off."
            ) from exc

        # CPU-Default fuer dev/test; auf dem Server kann via env auf GPU gehoben werden.
        self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
        return self._model

    def transcribe(
        self,
        audio_path: Path,
        language_hint: str | None = "de",
    ) -> TranscriptionResult:
        model = self._ensure_model()
        # language=None lässt faster-whisper die Sprache auto-detecten — wichtig
        # für mehrsprachige Eingaben (Türkisch, Russisch, Kurdisch etc.).
        segments, info = model.transcribe(
            str(audio_path),
            language=language_hint,  # None = auto-detect
            beam_size=5,
            vad_filter=True,
        )
        text_parts: list[str] = []
        for segment in segments:
            piece = getattr(segment, "text", "")
            if piece:
                text_parts.append(piece.strip())
        text = " ".join(part for part in text_parts if part).strip()
        language = getattr(info, "language", None) or language_hint
        return TranscriptionResult(text=text, language=language, provider=self.name)


class OpenAIWhisperApiProvider(WhisperProvider):
    """Remote-Transkription via OpenAI Whisper (``audio.transcriptions``).

    Verwendet den offiziellen ``openai``-Python-SDK. Der API-Key kommt aus
    ``settings.openai_api_key`` (Env-Var ``OPENAI_API_KEY``). Falls die
    Bibliothek nicht installiert ist, wirft der Provider einen sprechenden
    Fehler.
    """

    name = "openai-whisper"

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "whisper-1",
    ) -> None:
        self.api_key = api_key or settings.openai_api_key
        self.model_name = model_name
        self._client: Any | None = None

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY ist nicht gesetzt — der OpenAI-Whisper-Provider "
                "kann nicht starten."
            )
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:  # pragma: no cover — bibliotheksabhaengig
            raise RuntimeError(
                "Das `openai`-Package ist nicht installiert. Installiere `openai>=1.0` "
                "oder setze WHISPER_PROVIDER=local/off."
            ) from exc
        self._client = OpenAI(api_key=self.api_key)
        return self._client

    def transcribe(
        self,
        audio_path: Path,
        language_hint: str | None = "de",
    ) -> TranscriptionResult:
        client = self._ensure_client()
        # language_hint=None => kein language-Parameter senden, Whisper macht
        # dann Auto-Detect. Bei gesetztem Hint biast Whisper auf diese Sprache
        # (was bei nicht-deutsch sprechenden Monteuren ein Problem wäre).
        call_kwargs: dict[str, Any] = {
            "model": self.model_name,
            "response_format": "verbose_json",
        }
        if language_hint:
            call_kwargs["language"] = language_hint
        with audio_path.open("rb") as fh:
            call_kwargs["file"] = fh
            response = client.audio.transcriptions.create(**call_kwargs)
        # `response` ist ein typisiertes Pydantic-Model bzw. Dict — beides robust
        # auslesen, damit SDK-Versionen den Code nicht brechen.
        text = getattr(response, "text", None) or (
            response.get("text") if isinstance(response, dict) else ""
        ) or ""
        language = getattr(response, "language", None) or (
            response.get("language") if isinstance(response, dict) else None
        )
        return TranscriptionResult(
            text=text.strip(),
            language=language or language_hint,
            provider=self.name,
        )


class CodexAudioProvider(WhisperProvider):
    """Transkription via Codex CLI mit einem Audio-faehigen Modell.

    Codex CLI (``codex exec``) wird mit einem Prompt aufgerufen, der das
    referenzierte Audio-File liest und ausschliesslich den Transkript-Text
    auf stdout schreibt. Wir nutzen ein Audio-faehiges Modell (Default:
    ``settings.codex_audio_model`` falls gesetzt, sonst ``settings.codex_model``).

    Das Audio wird in ein Temp-Workspace-Verzeichnis kopiert, weil Codex
    ``--cd`` erwartet und nur dort lesen darf.
    """

    name = "codex-audio"

    def __init__(
        self,
        profile: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.profile = profile or settings.codex_profile
        self.model = model or settings.codex_audio_model or settings.codex_model
        self.timeout = timeout if timeout is not None else 300

    def _build_command(self, workspace_path: str) -> list[str]:
        command: list[str] = [
            "codex",
            "exec",
            "-p",
            self.profile,
            "--cd",
            workspace_path,
            "--skip-git-repo-check",
            "-",
        ]
        if self.model:
            command[2:2] = ["-m", self.model]
        return command

    def transcribe(
        self,
        audio_path: Path,
        language_hint: str | None = "de",
    ) -> TranscriptionResult:
        if not audio_path.exists():
            raise RuntimeError(f"Audio-Datei existiert nicht: {audio_path}")

        if shutil.which("codex") is None:
            raise RuntimeError(
                "Codex CLI ist nicht im PATH. Installiere `@openai/codex` "
                "oder setze einen anderen Whisper-Provider."
            )

        with tempfile.TemporaryDirectory(prefix="hez-codex-audio-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            local_audio = tmp_path / audio_path.name
            shutil.copy2(audio_path, local_audio)

            language_name = {"de": "Deutsch", "en": "Englisch"}.get(
                (language_hint or "de").lower(), language_hint or "Deutsch"
            )
            prompt = (
                f"Du sollst die Audio-Datei `{audio_path.name}` im aktuellen "
                f"Verzeichnis transkribieren. Sprache: {language_name}.\n\n"
                "Anweisungen:\n"
                "- Lies die Audio-Datei und transkribiere sie woertlich.\n"
                "- Bewahre Fachbegriffe (SHK, Heizung, Inbetriebnahme) korrekt.\n"
                "- Antworte AUSSCHLIESSLICH mit dem Transkript-Text — keine "
                "Einleitung, keine Erklaerung, kein Code-Fence.\n"
                "- Wenn die Datei keine Sprache enthaelt: antworte mit einer "
                "einzigen Zeile `[KEINE_SPRACHE_ERKANNT]`.\n"
            )

            try:
                process = subprocess.run(
                    self._build_command(str(tmp_path)),
                    input=prompt,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=self.timeout,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    f"Codex-Transkription Timeout nach {self.timeout}s"
                ) from exc

            if process.returncode != 0:
                raise RuntimeError(
                    f"Codex CLI returncode={process.returncode}: "
                    f"{(process.stderr or '').strip()[:500]}"
                )

            text = (process.stdout or "").strip()
            if not text:
                raise RuntimeError("Codex hat einen leeren Transkript-Text geliefert")
            if text == "[KEINE_SPRACHE_ERKANNT]":
                raise RuntimeError("Codex hat keine Sprache im Audio erkannt")

            return TranscriptionResult(
                text=text,
                language=language_hint,
                provider=self.name,
            )


class FallbackChainProvider(WhisperProvider):
    """Probiert mehrere Whisper-Provider in Reihenfolge.

    Jeder Provider wird genau einmal versucht. Wirft ein Provider einen Fehler,
    wird der naechste in der Kette probiert. Erst wenn alle scheitern, wird
    der zuletzt aufgetretene Fehler weitergereicht — mit Hinweis welche
    Provider verbraucht wurden.
    """

    name = "fallback-chain"

    def __init__(self, providers: list[WhisperProvider]) -> None:
        if not providers:
            raise ValueError("FallbackChainProvider braucht mindestens einen Provider")
        self.providers = providers
        # Name beschreibt die Kette, hilft beim Debuggen in transcript_provider.
        self.name = "+".join(provider.name for provider in providers)

    def transcribe(
        self,
        audio_path: Path,
        language_hint: str | None = "de",
    ) -> TranscriptionResult:
        errors: list[str] = []
        for provider in self.providers:
            try:
                result = provider.transcribe(audio_path, language_hint=language_hint)
                # Auf transcript_provider behalten wir den tatsaechlich erfolgreichen
                # Provider — wichtig fuer Audit/Diagnose welcher Fallback griff.
                return result
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Whisper-Provider %s fehlgeschlagen, naechster in der Kette: %s",
                    provider.name,
                    exc,
                )
                errors.append(f"{provider.name}: {exc}")

        raise RuntimeError(
            "Alle Whisper-Provider in der Kette sind fehlgeschlagen. " + " | ".join(errors)
        )


def _build_provider_from_name(name: str) -> WhisperProvider:
    """Map a single short identifier to a concrete provider instance."""
    key = name.strip().lower()
    if key == "local":
        return LocalFasterWhisperProvider()
    if key in ("openai", "openai-whisper", "whisper"):
        return OpenAIWhisperApiProvider()
    if key in ("codex", "codex-audio"):
        return CodexAudioProvider()
    if key in ("off", "null", "none"):
        return NullProvider()
    raise ValueError(f"Unbekannter Whisper-Provider-Name: {name!r}")


def get_whisper_provider() -> WhisperProvider:
    """Faktore, basierend auf ``settings.whisper_provider``.

    Spezialfaelle:
    - ``openai`` (Default-Empfehlung): OpenAI mit Codex als automatischem
      Fallback. Wenn OPENAI_API_KEY nicht gesetzt ist, faellt die Kette direkt
      auf Codex zurueck.
    - ``chain``: nutzt ``settings.whisper_chain`` (CSV) fuer eine custom Kette.
    """
    choice = (settings.whisper_provider or "off").strip().lower()

    if choice == "local":
        return LocalFasterWhisperProvider()

    if choice == "openai_only":
        return OpenAIWhisperApiProvider()

    if choice == "openai":
        # OpenAI primaer, Codex als Fallback. Wenn der Key fehlt, ist der
        # OpenAI-Provider beim ersten Call eh sofort failing, dann greift
        # automatisch Codex.
        return FallbackChainProvider(
            [OpenAIWhisperApiProvider(), CodexAudioProvider()]
        )

    if choice == "codex":
        return CodexAudioProvider()

    if choice == "chain":
        chain_csv = (settings.whisper_chain or "").strip()
        if not chain_csv:
            raise RuntimeError(
                "WHISPER_PROVIDER=chain gesetzt, aber WHISPER_CHAIN ist leer."
            )
        providers = [
            _build_provider_from_name(name)
            for name in chain_csv.split(",")
            if name.strip()
        ]
        if not providers:
            raise RuntimeError(
                "WHISPER_CHAIN enthaelt keinen gueltigen Provider-Namen."
            )
        return FallbackChainProvider(providers)

    return NullProvider()
