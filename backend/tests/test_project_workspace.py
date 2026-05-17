"""Tests for ``app.services.project_workspace`` (create + publish flows).

We use a temporary ``storage_root`` (via the ``workspace_root`` fixture) so
neither real project data nor host filesystem state leak between tests.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.models.project import ProjectCreate, ProjectSection
from app.services.output_validator import STANDARD_REQUIRED_FILES
from app.services.project_workspace import create_project_workspace, publish_project


def _project_create(slug: str = "demo-projekt") -> ProjectCreate:
    return ProjectCreate(
        slug=slug,
        name="Demo Projekt",
        project_type="standard",
        address=None,
        responsible=None,
        construction_manager=None,
        foreman=None,
        planned_start=None,
        planned_end=None,
        sections=[ProjectSection(number=1, name="Abschnitt 1")],
        notes=None,
    )


def _seed_output(output_dir: Path) -> None:
    """Materialise a minimum-valid role-based output tree."""
    for folder, files in STANDARD_REQUIRED_FILES.items():
        folder_path = output_dir / folder
        folder_path.mkdir(parents=True, exist_ok=True)
        for filename in files:
            (folder_path / filename).write_text(
                f"<html><!-- {filename} --></html>", encoding="utf-8"
            )
            if filename.endswith(".html"):
                md_name = f"{Path(filename).stem}.md"
                (folder_path / md_name).write_text(f"# {filename}\n", encoding="utf-8")


def test_create_project_workspace_writes_input_and_dirs(workspace_root: Path) -> None:
    project = _project_create("alpha")
    result = create_project_workspace(project)

    workspace_dir = workspace_root / "workspaces" / "alpha"
    assert Path(result.workspace_path) == workspace_dir
    assert (workspace_dir / "output").is_dir()
    assert (workspace_dir / "docs").is_dir()

    input_path = workspace_dir / "input.json"
    assert input_path.exists()
    assert "alpha" in input_path.read_text(encoding="utf-8")
    assert result.preview_url.endswith("alpha.hez.tech-artist.de") or "alpha." in result.preview_url


def test_create_project_workspace_is_idempotent(workspace_root: Path) -> None:
    """Calling twice for the same slug must not raise."""
    project = _project_create("beta")
    create_project_workspace(project)
    # Second call should overwrite the input.json without errors.
    create_project_workspace(project)
    assert (workspace_root / "workspaces" / "beta" / "input.json").exists()


def test_publish_project_copies_output_and_versions(workspace_root: Path) -> None:
    project = _project_create("gamma")
    workspace = create_project_workspace(project)
    _seed_output(Path(workspace.output_path))

    target = publish_project(slug="gamma", expected_section_count=1, project_type="standard")

    assert target == workspace_root / "projects" / "gamma"
    assert (target / "00_Start" / "index.html").exists()
    assert (target / "_versions").is_dir()
    versions = list((target / "_versions").iterdir())
    assert len(versions) == 1
    assert (versions[0] / "00_Start" / "index.html").exists()


def test_publish_project_with_invalid_output_raises(workspace_root: Path) -> None:
    project = _project_create("delta")
    create_project_workspace(project)
    # Note: do NOT seed the role-based output tree — validation must fail.
    with pytest.raises(Exception):
        publish_project(slug="delta", expected_section_count=1, project_type="standard")


def test_publish_project_keeps_history_across_versions(workspace_root: Path) -> None:
    project = _project_create("epsilon")
    workspace = create_project_workspace(project)
    _seed_output(Path(workspace.output_path))

    publish_project(slug="epsilon", expected_section_count=1, version_label="20260515T100000Z")
    publish_project(slug="epsilon", expected_section_count=1, version_label="20260515T110000Z")

    versions_dir = workspace_root / "projects" / "epsilon" / "_versions"
    version_names = sorted(child.name for child in versions_dir.iterdir())
    assert version_names == ["20260515T100000Z", "20260515T110000Z"]
