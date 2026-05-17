"""Unit-Tests fuer die Whisper-Provider-Strategy.

Die Provider-Libraries (``faster-whisper``, ``openai``) sind optionale
Dependencies — Tests, die sie tatsaechlich brauchen, ueberspringen sich
selbst, wenn die Lib nicht installiert ist. Die Auswahllogik via
``get_whisper_provider()`` und der ``NullProvider`` haben harte Assertions.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.settings import settings
from app.services import whisper_provider
from app.services.whisper_provider import (
    LocalFasterWhisperProvider,
    NullProvider,
    OpenAIWhisperApiProvider,
    TranscriptionResult,
    get_whisper_provider,
)


def test_null_provider_raises_with_clear_message(tmp_path: Path) -> None:
    provider = NullProvider()
    audio = tmp_path / "x.webm"
    audio.write_bytes(b"")
    with pytest.raises(RuntimeError) as info:
        provider.transcribe(audio)
    assert "WHISPER_PROVIDER" in str(info.value)


def test_get_whisper_provider_off_returns_null(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "whisper_provider", "off")
    provider = get_whisper_provider()
    assert isinstance(provider, NullProvider)
    assert provider.name == "null"


def test_get_whisper_provider_local_returns_faster_whisper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "whisper_provider", "local")
    provider = get_whisper_provider()
    assert isinstance(provider, LocalFasterWhisperProvider)
    assert provider.name == "local-faster-whisper"


def test_get_whisper_provider_openai_returns_chain_with_openai_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Neue Semantik: "openai" liefert eine FallbackChain mit OpenAI als
    # primaerem Provider und Codex als Fallback (siehe weitere Tests unten).
    from app.services.whisper_provider import FallbackChainProvider

    monkeypatch.setattr(settings, "whisper_provider", "openai")
    provider = get_whisper_provider()
    assert isinstance(provider, FallbackChainProvider)
    assert provider.providers[0].name == "openai-whisper"


def test_local_provider_loads_model_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bei fehlender Library wirft die erste transcribe() — nicht der Konstruktor."""
    provider = LocalFasterWhisperProvider(model_name="tiny")
    # Konstruktor darf NIE crashen, auch wenn faster_whisper fehlt.
    assert provider._model is None

    pytest.importorskip("faster_whisper")
    # Wenn die Lib da ist, koennen wir den Loader patchen statt echtes Modell zu laden.
    sentinel = object()
    monkeypatch.setattr(
        whisper_provider.LocalFasterWhisperProvider,
        "_ensure_model",
        lambda self: sentinel,
    )
    assert provider._ensure_model() is sentinel


def test_local_provider_transcribe_uses_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pytest.importorskip("faster_whisper")

    class _Segment:
        def __init__(self, text: str) -> None:
            self.text = text

    class _Info:
        language = "de"

    class _FakeModel:
        def transcribe(self, *args, **kwargs):  # noqa: D401, ANN001
            return iter([_Segment(" Vorlauf 65 Grad "), _Segment(" Ruecklauf 45.")]), _Info()

    provider = LocalFasterWhisperProvider(model_name="tiny")
    monkeypatch.setattr(provider, "_ensure_model", lambda: _FakeModel())

    audio = tmp_path / "voice.webm"
    audio.write_bytes(b"\x00")

    result = provider.transcribe(audio)
    assert isinstance(result, TranscriptionResult)
    assert "Vorlauf 65 Grad" in result.text
    assert "Ruecklauf 45." in result.text
    assert result.language == "de"
    assert result.provider == "local-faster-whisper"


def test_openai_provider_requires_api_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pytest.importorskip("openai")
    monkeypatch.setattr(settings, "openai_api_key", None)
    provider = OpenAIWhisperApiProvider(api_key=None)
    audio = tmp_path / "x.webm"
    audio.write_bytes(b"\x00")
    with pytest.raises(RuntimeError) as info:
        provider.transcribe(audio)
    assert "OPENAI_API_KEY" in str(info.value)


def test_openai_provider_calls_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pytest.importorskip("openai")

    class _Response:
        text = "Pumpe laeuft."
        language = "de"

    class _Transcriptions:
        def create(self, **kwargs):  # noqa: ANN001
            assert kwargs["model"] == "whisper-1"
            return _Response()

    class _Audio:
        transcriptions = _Transcriptions()

    class _FakeClient:
        audio = _Audio()

    provider = OpenAIWhisperApiProvider(api_key="sk-test")
    monkeypatch.setattr(provider, "_ensure_client", lambda: _FakeClient())

    audio = tmp_path / "voice.webm"
    audio.write_bytes(b"\x00")
    result = provider.transcribe(audio)
    assert result.text == "Pumpe laeuft."
    assert result.language == "de"
    assert result.provider == "openai-whisper"


# ---------------------------------------------------------------------------
# CodexAudioProvider + FallbackChainProvider (Phase 13.2 erweitert)
# ---------------------------------------------------------------------------


from app.services.whisper_provider import (
    CodexAudioProvider,
    FallbackChainProvider,
)


def test_codex_provider_raises_when_codex_cli_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = tmp_path / "voice.webm"
    audio.write_bytes(b"fake-audio")
    # Simuliere: codex ist nicht im PATH
    monkeypatch.setattr(
        "app.services.whisper_provider.shutil.which",
        lambda name: None,
    )
    provider = CodexAudioProvider()
    with pytest.raises(RuntimeError) as exc:
        provider.transcribe(audio)
    assert "Codex CLI" in str(exc.value)


def test_codex_provider_raises_when_audio_missing(tmp_path: Path) -> None:
    provider = CodexAudioProvider()
    with pytest.raises(RuntimeError) as exc:
        provider.transcribe(tmp_path / "nope.webm")
    assert "existiert nicht" in str(exc.value)


def test_codex_provider_returns_stdout_as_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = tmp_path / "voice.webm"
    audio.write_bytes(b"fake-audio-bytes")

    monkeypatch.setattr(
        "app.services.whisper_provider.shutil.which",
        lambda name: "/usr/local/bin/codex",
    )

    class FakeCompleted:
        returncode = 0
        stdout = "Vorlauf 65 Grad, Ruecklauf 45 Grad, Anlage dicht.\n"
        stderr = ""

    monkeypatch.setattr(
        "app.services.whisper_provider.subprocess.run",
        lambda *args, **kwargs: FakeCompleted(),
    )

    result = CodexAudioProvider().transcribe(audio)
    assert "Vorlauf 65 Grad" in result.text
    assert result.provider == "codex-audio"


def test_codex_provider_raises_on_no_speech_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = tmp_path / "silence.webm"
    audio.write_bytes(b"silent")

    monkeypatch.setattr(
        "app.services.whisper_provider.shutil.which",
        lambda name: "/usr/local/bin/codex",
    )

    class FakeCompleted:
        returncode = 0
        stdout = "[KEINE_SPRACHE_ERKANNT]"
        stderr = ""

    monkeypatch.setattr(
        "app.services.whisper_provider.subprocess.run",
        lambda *args, **kwargs: FakeCompleted(),
    )

    with pytest.raises(RuntimeError) as exc:
        CodexAudioProvider().transcribe(audio)
    assert "Sprache" in str(exc.value)


def test_fallback_chain_uses_first_successful_provider(tmp_path: Path) -> None:
    audio = tmp_path / "voice.webm"
    audio.write_bytes(b"fake")

    class FailingProvider(WhisperProviderBase := __import__(
        "app.services.whisper_provider", fromlist=["WhisperProvider"]
    ).WhisperProvider):
        name = "fail"

        def transcribe(self, audio_path, language_hint="de"):
            raise RuntimeError("primary down")

    class SuccessProvider(WhisperProviderBase):
        name = "ok"

        def transcribe(self, audio_path, language_hint="de"):
            return TranscriptionResult(text="hallo welt", language="de", provider=self.name)

    chain = FallbackChainProvider([FailingProvider(), SuccessProvider()])
    result = chain.transcribe(audio)
    assert result.text == "hallo welt"
    # Der erfolgreiche Provider-Name landet im Result, nicht der Ketten-Name.
    assert result.provider == "ok"


def test_fallback_chain_aggregates_errors_when_all_fail(tmp_path: Path) -> None:
    audio = tmp_path / "voice.webm"
    audio.write_bytes(b"fake")

    class FailingProvider(__import__(
        "app.services.whisper_provider", fromlist=["WhisperProvider"]
    ).WhisperProvider):
        def __init__(self, name: str, message: str) -> None:
            self.name = name
            self._message = message

        def transcribe(self, audio_path, language_hint="de"):
            raise RuntimeError(self._message)

    chain = FallbackChainProvider(
        [FailingProvider("a", "boom-a"), FailingProvider("b", "boom-b")]
    )
    with pytest.raises(RuntimeError) as exc:
        chain.transcribe(audio)
    assert "boom-a" in str(exc.value) and "boom-b" in str(exc.value)


def test_get_whisper_provider_openai_returns_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "whisper_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    provider = get_whisper_provider()
    assert isinstance(provider, FallbackChainProvider)
    assert provider.providers[0].name == "openai-whisper"
    assert provider.providers[1].name == "codex-audio"


def test_get_whisper_provider_openai_only_skips_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "whisper_provider", "openai_only")
    provider = get_whisper_provider()
    assert isinstance(provider, OpenAIWhisperApiProvider)


def test_get_whisper_provider_codex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "whisper_provider", "codex")
    provider = get_whisper_provider()
    assert isinstance(provider, CodexAudioProvider)


def test_get_whisper_provider_chain_parses_csv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "whisper_provider", "chain")
    monkeypatch.setattr(settings, "whisper_chain", "codex,local")
    provider = get_whisper_provider()
    assert isinstance(provider, FallbackChainProvider)
    names = [p.name for p in provider.providers]
    assert "codex-audio" in names
    assert "local-faster-whisper" in names
