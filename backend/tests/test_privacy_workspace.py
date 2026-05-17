"""Tests for ``app.services.privacy_workspace``.

We swap ``pii_tokenizer.tokenize`` with a fake that returns a deterministic
placeholder; that keeps the test focused on workspace orchestration
(directory layout, manifest contents, sync) without depending on the
fallback regex or any external ML model.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.db.orm_models import AnonymizationRun
from app.services import privacy_workspace
from app.services.privacy_workspace import (
    prepare_sanitized_generator_workspace,
    sync_generator_output,
)


class _FakeTokenizer:
    """A drop-in replacement for ``pii_tokenizer`` used by ``privacy_workspace``."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self._counter = 0

    def tokenize(self, db, text, scope=None, mode="internal"):
        self._counter += 1
        self.calls.append((text, scope))
        run = AnonymizationRun(run_id=f"fakerun{self._counter:04d}", scope=scope, mode=mode)
        db.add(run)
        db.flush()
        sanitized = f"[[FAKE_TOKENIZED:{self._counter}]] " + text
        return run, sanitized


@pytest.fixture()
def fake_tokenizer(monkeypatch: pytest.MonkeyPatch) -> _FakeTokenizer:
    fake = _FakeTokenizer()
    monkeypatch.setattr(privacy_workspace, "pii_tokenizer", fake)
    return fake


def _bootstrap_project_workspace(root: Path, slug: str) -> Path:
    workspace = root / "workspaces" / slug
    (workspace / "docs").mkdir(parents=True)
    (workspace / "output").mkdir(parents=True)
    (workspace / "input.json").write_text(
        json.dumps({"slug": slug, "name": "Demo"}, ensure_ascii=False),
        encoding="utf-8",
    )
    return workspace


def test_prepare_sanitized_workspace_creates_expected_layout(
    workspace_root: Path, db_session, fake_tokenizer: _FakeTokenizer
) -> None:
    workspace = _bootstrap_project_workspace(workspace_root, "demo")
    (workspace / "docs" / "notes.txt").write_text(
        "Bauleiter heisst Max Mustermann.", encoding="utf-8"
    )

    generator_path = prepare_sanitized_generator_workspace(db_session, "demo")

    assert generator_path == workspace / "generator_input"
    assert (generator_path / "docs").is_dir()
    assert (generator_path / "output").is_dir()
    assert (generator_path / "input.json").exists()
    assert (generator_path / "docs" / "notes.txt").exists()
    assert (generator_path / "privacy_manifest.json").exists()


def test_prepare_sanitized_workspace_writes_manifest(
    workspace_root: Path, db_session, fake_tokenizer: _FakeTokenizer
) -> None:
    workspace = _bootstrap_project_workspace(workspace_root, "demo")
    (workspace / "docs" / "notes.txt").write_text("Hallo Welt", encoding="utf-8")
    (workspace / "docs" / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    prepare_sanitized_generator_workspace(db_session, "demo")
    manifest = json.loads(
        (workspace / "generator_input" / "privacy_manifest.json").read_text(encoding="utf-8")
    )

    tokenized_paths = {entry["path"] for entry in manifest["tokenized_files"]}
    excluded_paths = {entry["path"] for entry in manifest["excluded_files"]}

    # input.json + notes.txt are tokenizable; the PNG is excluded.
    assert "notes.txt" in tokenized_paths
    assert any("input.json" in path for path in tokenized_paths)
    assert "image.png" in excluded_paths


def test_prepare_sanitized_workspace_recreates_clean_state(
    workspace_root: Path, db_session, fake_tokenizer: _FakeTokenizer
) -> None:
    workspace = _bootstrap_project_workspace(workspace_root, "demo")
    (workspace / "docs" / "notes.txt").write_text("foo", encoding="utf-8")

    # Pre-create a stale generator_input/ to be wiped on next prepare call.
    stale_path = workspace / "generator_input" / "old.txt"
    stale_path.parent.mkdir(parents=True, exist_ok=True)
    stale_path.write_text("stale", encoding="utf-8")

    prepare_sanitized_generator_workspace(db_session, "demo")

    assert not stale_path.exists(), "Old generator_input artefacts must be cleared"


def test_sync_generator_output_copies_into_workspace_output(workspace_root: Path) -> None:
    workspace = _bootstrap_project_workspace(workspace_root, "demo")
    generator_output = workspace / "generator_input" / "output"
    generator_output.mkdir(parents=True)
    (generator_output / "index.html").write_text("<html/>", encoding="utf-8")
    (generator_output / "subdir").mkdir()
    (generator_output / "subdir" / "child.txt").write_text("hi", encoding="utf-8")

    # Prime workspace output with a stale file that must be removed.
    (workspace / "output" / "stale.txt").write_text("stale", encoding="utf-8")

    sync_generator_output("demo")

    assert (workspace / "output" / "index.html").exists()
    assert (workspace / "output" / "subdir" / "child.txt").exists()
    assert not (workspace / "output" / "stale.txt").exists()


def test_sync_generator_output_is_noop_when_no_generator_output(workspace_root: Path) -> None:
    _bootstrap_project_workspace(workspace_root, "demo")
    # Should silently do nothing if there is no generator_input/output yet.
    sync_generator_output("demo")
