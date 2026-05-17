"""Tests for the role-based output filter in ``app.api.projects``.

The helpers ``_list_output_files``, ``_list_output_versions`` and
``_safe_output_path`` take an optional ``allowed_folders`` argument that
maps to the role-to-folder table in ``app.services.auth``.

The tests materialise a small role-based output tree under a per-test
``workspace_root`` and then verify that:

- monteurs only see ``00_Start``, ``01_Monteur`` and ``05_Allgemein``,
- bauleitung additionally sees ``02_Obermonteur`` and ``03_Bauleitung``,
- projektleitung (allowed_folders is None) sees everything, and
- requesting a non-allowed file directly raises HTTP 403.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.projects import (
    _list_output_files,
    _list_output_versions,
    _safe_output_path,
)
from app.services.auth import allowed_output_folders


ALL_FOLDERS = [
    "00_Start",
    "01_Monteur",
    "02_Obermonteur",
    "03_Bauleitung",
    "04_Projektleitung",
    "05_Allgemein",
]


def _seed_output_tree(workspace_root: Path, slug: str) -> Path:
    """Materialise one .html file per role folder so we can filter on it."""
    project_root = workspace_root / "projects" / slug
    for folder in ALL_FOLDERS:
        folder_path = project_root / folder
        folder_path.mkdir(parents=True, exist_ok=True)
        (folder_path / "index.html").write_text(f"<!-- {folder} -->", encoding="utf-8")

    versions_root = project_root / "_versions" / "run-1"
    for folder in ALL_FOLDERS:
        folder_path = versions_root / folder
        folder_path.mkdir(parents=True, exist_ok=True)
        (folder_path / "index.html").write_text(f"<!-- v1 {folder} -->", encoding="utf-8")

    return project_root


def _paths_of(files) -> set[str]:
    return {file.path for file in files}


def test_monteur_sees_only_monteur_relevant_folders(workspace_root: Path) -> None:
    _seed_output_tree(workspace_root, "rbac-monteur")
    allowed = allowed_output_folders("monteur")
    assert allowed == frozenset({"00_Start", "01_Monteur", "05_Allgemein"})

    files = _list_output_files("rbac-monteur", allowed)
    seen_folders = {file.path.split("/", 1)[0] for file in files}
    assert seen_folders == {"00_Start", "01_Monteur", "05_Allgemein"}


def test_obermonteur_sees_monteur_plus_obermonteur(workspace_root: Path) -> None:
    _seed_output_tree(workspace_root, "rbac-ober")
    allowed = allowed_output_folders("obermonteur")

    files = _list_output_files("rbac-ober", allowed)
    seen_folders = {file.path.split("/", 1)[0] for file in files}
    assert seen_folders == {"00_Start", "01_Monteur", "02_Obermonteur", "05_Allgemein"}


def test_bauleitung_sees_monteur_plus_obermonteur_plus_bauleitung(workspace_root: Path) -> None:
    _seed_output_tree(workspace_root, "rbac-bau")
    allowed = allowed_output_folders("bauleitung")

    files = _list_output_files("rbac-bau", allowed)
    seen_folders = {file.path.split("/", 1)[0] for file in files}
    assert seen_folders == {
        "00_Start",
        "01_Monteur",
        "02_Obermonteur",
        "03_Bauleitung",
        "05_Allgemein",
    }


def test_projektleitung_and_admin_see_all_folders(workspace_root: Path) -> None:
    _seed_output_tree(workspace_root, "rbac-pl")
    # allowed_output_folders returns None when all are visible.
    assert allowed_output_folders("projektleitung") is None
    assert allowed_output_folders("admin") is None
    assert allowed_output_folders("viewer") is None

    files = _list_output_files("rbac-pl", None)
    seen_folders = {file.path.split("/", 1)[0] for file in files}
    assert seen_folders == set(ALL_FOLDERS)


def test_unknown_role_sees_nothing(workspace_root: Path) -> None:
    """Defensive: unknown roles are treated restrictively (empty frozenset)."""
    _seed_output_tree(workspace_root, "rbac-unknown")
    allowed = allowed_output_folders("ghost-role")
    assert allowed == frozenset()

    files = _list_output_files("rbac-unknown", allowed)
    assert files == []


def test_direct_file_access_to_disallowed_folder_raises_403(workspace_root: Path) -> None:
    _seed_output_tree(workspace_root, "rbac-403")
    allowed = allowed_output_folders("monteur")

    with pytest.raises(HTTPException) as excinfo:
        _safe_output_path("rbac-403", "03_Bauleitung/index.html", allowed)
    assert excinfo.value.status_code == 403


def test_direct_file_access_to_allowed_folder_returns_path(workspace_root: Path) -> None:
    project_root = _seed_output_tree(workspace_root, "rbac-ok")
    allowed = allowed_output_folders("monteur")

    resolved = _safe_output_path("rbac-ok", "01_Monteur/index.html", allowed)
    assert resolved == (project_root / "01_Monteur" / "index.html").resolve()


def test_version_listing_filters_files_for_monteur(workspace_root: Path) -> None:
    _seed_output_tree(workspace_root, "rbac-ver")
    allowed = allowed_output_folders("monteur")

    versions = _list_output_versions("rbac-ver", allowed)
    assert len(versions) == 1
    # monteur sees 3 of the 6 folders -> 3 files
    assert versions[0].file_count == 3


def test_version_listing_unfiltered_counts_all_for_admin(workspace_root: Path) -> None:
    _seed_output_tree(workspace_root, "rbac-ver-admin")
    versions = _list_output_versions("rbac-ver-admin", None)
    assert len(versions) == 1
    assert versions[0].file_count == len(ALL_FOLDERS)
