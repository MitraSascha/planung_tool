"""Tests fuer die Foto-Doku-Schicht (Phase 12).

Wir testen drei Aspekte direkt gegen die Service-Helfer in
``app.api.media`` und die ORM-Schicht — ohne FastAPI-Routing, weil das
Auth-Setup hier nichts beitraegt und die eigentlichen Helfer eh die
ganze Logik tragen:

1. EXIF-Extraktion mit einem programmatisch erzeugten Mini-JPEG (Pillow
   muss installiert sein — sonst skip).
2. SHA-256 ist deterministisch (gleiche Bytes -> gleicher Hash).
3. Upload + List + Patch + Delete-Flow durch direktes Manipulieren der
   ORM-Schicht + ``settings.uploads_path`` auf ``tmp_path``.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path

import pytest

from app.api.media import _extract_exif, _sha256
from app.db.orm_models import Project, ProjectPhoto, User

try:  # Pillow ist optional; alle EXIF-Tests werden ohne Pillow geskippt.
    from PIL import Image  # type: ignore[import]

    HAS_PIL = True
except Exception:  # pragma: no cover - exercised only on hosts ohne Pillow
    HAS_PIL = False


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_jpeg(width: int = 4, height: int = 4) -> bytes:
    """Programmatisch ein winziges JPEG erzeugen (kein EXIF noetig)."""
    if not HAS_PIL:
        raise RuntimeError("Pillow ist nicht installiert")
    image = Image.new("RGB", (width, height), color=(180, 200, 220))
    buf = BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()


def _make_user(db_session, username: str = "tester") -> User:
    user = User(
        username=username,
        display_name=username.capitalize(),
        password_hash="x",
        global_role="admin",
        active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _make_project(db_session, slug: str = "demo") -> Project:
    project = Project(slug=slug, name="Demo", project_type="standard")
    db_session.add(project)
    db_session.flush()
    return project


# ---------------------------------------------------------------------------
# SHA-256 ist deterministisch
# ---------------------------------------------------------------------------


def test_sha256_is_deterministic_for_same_bytes() -> None:
    data = b"deterministic-bytes-for-test"
    first = _sha256(data)
    second = _sha256(data)
    assert first == second
    # Sanity-Check gegen Stdlib.
    assert first == hashlib.sha256(data).hexdigest()


def test_sha256_changes_for_different_bytes() -> None:
    assert _sha256(b"alpha") != _sha256(b"beta")


# ---------------------------------------------------------------------------
# EXIF-Extraktion
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_PIL, reason="Pillow nicht installiert")
def test_extract_exif_returns_dimensions_for_minimal_jpeg() -> None:
    jpeg = _make_jpeg(width=8, height=6)
    result = _extract_exif(jpeg)
    assert result.get("width") == 8
    assert result.get("height") == 6


def test_extract_exif_returns_empty_for_invalid_input() -> None:
    # Auch ohne Pillow muss die Funktion graceful zurueckkommen.
    assert _extract_exif(b"not-an-image") == {}


# ---------------------------------------------------------------------------
# Upload + List + Patch + Delete (gegen ORM + Filesystem)
# ---------------------------------------------------------------------------


def test_photo_lifecycle_upload_list_patch_delete(
    db_session, workspace_root: Path
) -> None:
    user = _make_user(db_session)
    project = _make_project(db_session, slug="lifecycle")
    db_session.commit()

    # Schritt 1: Simulierter Upload — wie ``upload_photo`` es macht, aber
    # ohne FastAPI-Dispatch.
    data = b"fake-jpeg-content"
    digest = _sha256(data)
    photos_dir = workspace_root / "uploads" / "photos" / project.slug
    photos_dir.mkdir(parents=True, exist_ok=True)
    target = photos_dir / f"{digest[:12]}.jpg"
    target.write_bytes(data)

    photo = ProjectPhoto(
        project_id=project.id,
        section_number=1,
        user_id=user.id,
        filename="raw.jpg",
        path=str(target),
        content_type="image/jpeg",
        sha256=digest,
        width=None,
        height=None,
        caption="Erste Aufnahme",
    )
    db_session.add(photo)
    db_session.commit()
    photo_id = photo.id

    # Schritt 2: Liste mit Filter ``section_number``.
    listed = (
        db_session.query(ProjectPhoto)
        .filter(
            ProjectPhoto.project_id == project.id,
            ProjectPhoto.section_number == 1,
        )
        .all()
    )
    assert len(listed) == 1
    assert listed[0].sha256 == digest
    assert listed[0].caption == "Erste Aufnahme"

    # Schritt 3: Patch — Caption ueberschreiben, Section umhaengen.
    photo.caption = "Aktualisierte Caption"
    photo.section_number = 2
    db_session.commit()
    db_session.refresh(photo)
    assert photo.caption == "Aktualisierte Caption"
    assert photo.section_number == 2

    # Schritt 4: Liste mit dem alten Filter findet das Foto nicht mehr.
    listed_after_patch = (
        db_session.query(ProjectPhoto)
        .filter(
            ProjectPhoto.project_id == project.id,
            ProjectPhoto.section_number == 1,
        )
        .all()
    )
    assert listed_after_patch == []

    # Schritt 5: Delete — Datei + ORM-Eintrag verschwinden.
    Path(photo.path).unlink(missing_ok=True)
    db_session.delete(photo)
    db_session.commit()

    assert (
        db_session.query(ProjectPhoto).filter(ProjectPhoto.id == photo_id).one_or_none()
        is None
    )
    assert not target.exists()


def test_photo_can_filter_by_daily_report_id(
    db_session, workspace_root: Path
) -> None:
    """Filter nach ``daily_report_id`` ist die Grundlage der Galerie-Anzeige
    im Tagesbericht-Detailpanel."""
    user = _make_user(db_session, username="reporter")
    project = _make_project(db_session, slug="filter")
    db_session.commit()

    photo_a = ProjectPhoto(
        project_id=project.id,
        user_id=user.id,
        daily_report_id=42,
        filename="a.jpg",
        path="/tmp/a.jpg",
        sha256="a" * 64,
    )
    photo_b = ProjectPhoto(
        project_id=project.id,
        user_id=user.id,
        daily_report_id=None,
        filename="b.jpg",
        path="/tmp/b.jpg",
        sha256="b" * 64,
    )
    db_session.add_all([photo_a, photo_b])
    db_session.commit()

    matching = (
        db_session.query(ProjectPhoto)
        .filter(ProjectPhoto.daily_report_id == 42)
        .all()
    )
    assert len(matching) == 1
    assert matching[0].filename == "a.jpg"
