"""Tests fuer ``write_voice_notes_to_workspace``."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.db.orm_models import Project, User, VoiceNote
from app.services.project_workspace import write_voice_notes_to_workspace


def _make_note(
    *,
    id_: int,
    status: str,
    transcript: str | None,
    intent: str = "freitext",
    username: str | None = None,
) -> VoiceNote:
    note = VoiceNote(
        id=id_,
        project_id=1,
        audio_path=f"/tmp/{id_}.webm",
        intent=intent,
        transcript=transcript,
        transcription_status=status,
    )
    note.created_at = datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc)
    if username:
        note.user = User(id=1, username=username, display_name=username, password_hash="x")
    return note


def test_write_voice_notes_creates_json(workspace_root: Path) -> None:
    workspace_dir = workspace_root / "workspaces" / "demo"
    workspace_dir.mkdir(parents=True)
    notes = [
        _make_note(id_=1, status="ok", transcript="Vorlauf 65 Grad.", intent="ibn", username="anna"),
        _make_note(id_=2, status="ok", transcript="Uebergabe abgeschlossen.", intent="uebergabe"),
    ]
    target = write_voice_notes_to_workspace("demo", notes)
    assert target == workspace_dir / "voice_notes.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    assert len(data) == 2
    assert data[0] == {
        "id": 1,
        "intent": "ibn",
        "transcript": "Vorlauf 65 Grad.",
        "transcript_language": None,
        "transcript_provider": None,
        "created_at": "2026-05-15T10:00:00+00:00",
        "username": "anna",
    }
    assert data[1]["intent"] == "uebergabe"


def test_write_voice_notes_skips_non_ok_and_empty(workspace_root: Path) -> None:
    workspace_dir = workspace_root / "workspaces" / "beta"
    workspace_dir.mkdir(parents=True)
    notes = [
        _make_note(id_=1, status="pending", transcript=None),
        _make_note(id_=2, status="failed", transcript="x"),
        _make_note(id_=3, status="ok", transcript=""),
        _make_note(id_=4, status="ok", transcript="   "),
        _make_note(id_=5, status="ok", transcript="ok hier."),
    ]
    target = write_voice_notes_to_workspace("beta", notes)
    assert target is not None
    data = json.loads(target.read_text(encoding="utf-8"))
    assert [entry["id"] for entry in data] == [5]


def test_write_voice_notes_removes_file_when_no_data(workspace_root: Path) -> None:
    workspace_dir = workspace_root / "workspaces" / "gamma"
    workspace_dir.mkdir(parents=True)
    stale = workspace_dir / "voice_notes.json"
    stale.write_text("[]", encoding="utf-8")

    target = write_voice_notes_to_workspace(
        "gamma",
        [_make_note(id_=1, status="failed", transcript="x")],
    )
    assert target is None
    assert not stale.exists()


def test_write_voice_notes_handles_empty_list(workspace_root: Path) -> None:
    workspace_dir = workspace_root / "workspaces" / "delta"
    workspace_dir.mkdir(parents=True)
    assert write_voice_notes_to_workspace("delta", []) is None
    assert not (workspace_dir / "voice_notes.json").exists()
