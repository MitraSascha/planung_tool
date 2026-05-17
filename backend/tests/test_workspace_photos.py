"""Tests fuer ``copy_photos_to_workspace`` und die Photo-Veroeffentlichung
in ``publish_project``.

Es wird kein echtes Photo-EXIF gebraucht — die Funktion arbeitet auf
``ProjectPhoto``-Instanzen (ORM) und kopiert die Dateien anhand der
gespeicherten Pfade. Wir erzeugen also dummy-Files an
``photo.path`` und pruefen Manifest + Filesystem.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.db.orm_models import ProjectPhoto
from app.models.project import ProjectCreate, ProjectSection
from app.services.output_validator import STANDARD_REQUIRED_FILES
from app.services.project_workspace import (
    copy_photos_to_workspace,
    create_project_workspace,
    publish_project,
)


def _make_photo(
    source_path: Path,
    *,
    photo_id: int = 1,
    section_number: int | None = 1,
    daily_report_id: int | None = None,
    caption: str | None = None,
    sha256: str = "abc123def456ffffffff" + "0" * 44,
    annotated_path: str | None = None,
    filename: str = "site.jpg",
) -> ProjectPhoto:
    """Build a transient ORM instance without touching the DB. Attribute
    access is identical, which is what ``copy_photos_to_workspace`` needs."""
    photo = ProjectPhoto(
        project_id=1,
        section_number=section_number,
        daily_report_id=daily_report_id,
        user_id=None,
        filename=filename,
        path=str(source_path),
        annotated_path=annotated_path,
        content_type="image/jpeg",
        sha256=sha256,
        width=640,
        height=480,
        taken_at=datetime(2026, 5, 15, 10, 30, tzinfo=timezone.utc),
        geo_lat=52.5,
        geo_lng=13.4,
        caption=caption,
    )
    photo.id = photo_id
    return photo


def _project_create(slug: str = "demo-foto") -> ProjectCreate:
    return ProjectCreate(
        slug=slug,
        name="Demo Foto Projekt",
        project_type="standard",
        sections=[ProjectSection(number=1, name="Abschnitt 1")],
    )


def _seed_output(output_dir: Path) -> None:
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


def test_copy_photos_to_workspace_creates_manifest_and_files(workspace_root: Path) -> None:
    slug = "alpha"
    workspace = workspace_root / "workspaces" / slug
    workspace.mkdir(parents=True, exist_ok=True)

    source_dir = workspace_root / "uploads" / "photos" / slug
    source_dir.mkdir(parents=True, exist_ok=True)
    source_file = source_dir / "raw.jpg"
    source_file.write_bytes(b"fake-jpeg-bytes")

    photo = _make_photo(
        source_file,
        section_number=2,
        caption="Heizraum nach Demontage",
    )

    result = copy_photos_to_workspace(slug, [photo])

    assert result == workspace / "photos"
    photos_dir = workspace / "photos"
    assert photos_dir.is_dir()
    copied = list(photos_dir.iterdir())
    assert len(copied) == 1
    assert copied[0].read_bytes() == b"fake-jpeg-bytes"

    manifest_path = workspace / "photos.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest) == 1
    entry = manifest[0]
    assert entry["section_number"] == 2
    assert entry["caption"] == "Heizraum nach Demontage"
    assert entry["relative_path"].startswith("photos/")
    assert entry["taken_at"].startswith("2026-05-15")
    assert entry["geo_lat"] == 52.5
    assert entry["geo_lng"] == 13.4


def test_copy_photos_to_workspace_prefers_annotated_when_set(workspace_root: Path) -> None:
    slug = "annotated"
    workspace = workspace_root / "workspaces" / slug
    workspace.mkdir(parents=True, exist_ok=True)

    source_dir = workspace_root / "uploads" / "photos" / slug
    source_dir.mkdir(parents=True, exist_ok=True)

    raw = source_dir / "raw.jpg"
    raw.write_bytes(b"raw-bytes")
    annotated = source_dir / "annotated.png"
    annotated.write_bytes(b"annotated-bytes")

    photo = _make_photo(raw, annotated_path=str(annotated))
    copy_photos_to_workspace(slug, [photo])

    photos_dir = workspace / "photos"
    copied = list(photos_dir.iterdir())
    assert len(copied) == 1
    assert copied[0].read_bytes() == b"annotated-bytes"

    manifest = json.loads((workspace / "photos.json").read_text(encoding="utf-8"))
    assert manifest[0]["is_annotated"] is True


def test_copy_photos_to_workspace_empty_list_removes_artefacts(
    workspace_root: Path,
) -> None:
    slug = "empty"
    workspace = workspace_root / "workspaces" / slug
    photos_dir = workspace / "photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    (photos_dir / "stale.jpg").write_bytes(b"stale")
    (workspace / "photos.json").write_text("[]", encoding="utf-8")

    result = copy_photos_to_workspace(slug, [])

    assert result is None
    assert not photos_dir.exists()
    assert not (workspace / "photos.json").exists()


def test_copy_photos_to_workspace_skips_missing_source(workspace_root: Path) -> None:
    slug = "missing"
    workspace = workspace_root / "workspaces" / slug
    workspace.mkdir(parents=True, exist_ok=True)

    photo = _make_photo(Path("/does/not/exist.jpg"))
    copy_photos_to_workspace(slug, [photo])

    photos_dir = workspace / "photos"
    # Manifest must still be written (zero entries is fine), but no file copy.
    assert photos_dir.is_dir()
    assert list(photos_dir.iterdir()) == []
    manifest = json.loads((workspace / "photos.json").read_text(encoding="utf-8"))
    assert manifest == []


def test_publish_project_copies_photos_into_public_dir(workspace_root: Path) -> None:
    slug = "publish-photos"
    project = _project_create(slug)
    workspace = create_project_workspace(project)
    _seed_output(Path(workspace.output_path))

    workspace_dir = workspace_root / "workspaces" / slug
    photos_dir = workspace_dir / "photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    (photos_dir / "abc.jpg").write_bytes(b"public-bytes")

    target = publish_project(slug=slug, expected_section_count=1)
    assert (target / "photos" / "abc.jpg").exists()
    assert (target / "photos" / "abc.jpg").read_bytes() == b"public-bytes"


def test_publish_project_without_photos_does_not_create_folder(
    workspace_root: Path,
) -> None:
    slug = "no-photos"
    project = _project_create(slug)
    workspace = create_project_workspace(project)
    _seed_output(Path(workspace.output_path))

    target = publish_project(slug=slug, expected_section_count=1)
    assert not (target / "photos").exists()
