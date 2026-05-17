"""Tests for ``app.services.output_validator.validate_project_output``.

The validator enforces the role-based output structure laid out in
``planung/ZIELSTRUKTUR.md``: 00_Start/, 01_Monteur/, 02_Obermonteur/,
03_Bauleitung/, 04_Projektleitung/, 05_Allgemein/ mit ``<ROLLE>_<INHALT>.html``
als alleinige Zielformate.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.output_validator import (
    OutputValidationError,
    SMALL_REQUIRED_FILES,
    STANDARD_REQUIRED_FILES,
    validate_project_output,
)


def _materialise(output_root: Path, layout: dict[str, tuple[str, ...]]) -> None:
    """Create every required HTML file under output_root."""
    for folder, files in layout.items():
        folder_path = output_root / folder
        folder_path.mkdir(parents=True, exist_ok=True)
        for filename in files:
            (folder_path / filename).write_text(f"<html><!-- {filename} --></html>", encoding="utf-8")


def test_validate_passes_on_complete_standard_output(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    _materialise(output_dir, STANDARD_REQUIRED_FILES)

    # Should not raise.
    validate_project_output(output_dir, expected_section_count=3, project_type="standard")


def test_validate_passes_on_complete_small_output(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    _materialise(output_dir, SMALL_REQUIRED_FILES)

    validate_project_output(output_dir, expected_section_count=1, project_type="small")


def test_validate_raises_when_output_dir_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    with pytest.raises(OutputValidationError) as excinfo:
        validate_project_output(missing, expected_section_count=1, project_type="standard")
    assert any("does not exist" in err for err in excinfo.value.errors)


def test_validate_reports_missing_folder(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    layout = {key: files for key, files in STANDARD_REQUIRED_FILES.items() if key != "03_Bauleitung"}
    _materialise(output_dir, layout)

    with pytest.raises(OutputValidationError) as excinfo:
        validate_project_output(output_dir, expected_section_count=1, project_type="standard")
    assert any("03_Bauleitung" in err for err in excinfo.value.errors)


def test_validate_reports_missing_html_file(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    _materialise(output_dir, STANDARD_REQUIRED_FILES)
    # Remove one required HTML to trigger the missing-file path.
    target = output_dir / "01_Monteur" / "MONTEUR_Tagescheckliste.html"
    target.unlink()

    with pytest.raises(OutputValidationError) as excinfo:
        validate_project_output(output_dir, expected_section_count=1, project_type="standard")
    assert any("MONTEUR_Tagescheckliste.html" in err for err in excinfo.value.errors)


