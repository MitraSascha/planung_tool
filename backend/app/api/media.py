import hashlib
from datetime import datetime
from pathlib import Path
from typing import Iterable

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload

from app.core.settings import settings
from app.db.database import get_db
from app.db.orm_models import Project, ProjectPhoto, User, VoiceNote
from app.models.media import (
    ProjectPhotoRead,
    ProjectPhotoUpdate,
    VoiceNoteRead,
    VoiceNoteUpdate,
)
from app.services.auth import (
    PROJECT_READ_ROLES,
    get_current_user,
    require_project_role,
)

router = APIRouter()


ALLOWED_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
ALLOWED_AUDIO_EXTENSIONS = {".webm", ".mp3", ".m4a", ".wav", ".ogg", ".opus"}


def _project_or_404(db: Session, slug: str) -> Project:
    project = db.query(Project).filter(Project.slug == slug).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _safe_extension(filename: str, allowed: Iterable[str]) -> str:
    suffix = Path(filename or "upload").suffix.lower()
    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type {suffix}. Allowed: {', '.join(sorted(allowed))}",
        )
    return suffix


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Photos
# ---------------------------------------------------------------------------


def _photo_view_url(slug: str, photo_id: int) -> str:
    return f"/api/projects/{slug}/photos/{photo_id}/raw"


def _photo_annotated_url(slug: str, photo_id: int) -> str | None:
    return f"/api/projects/{slug}/photos/{photo_id}/annotated"


def _photo_to_read(photo: ProjectPhoto, slug: str) -> ProjectPhotoRead:
    return ProjectPhotoRead(
        id=photo.id,
        project_slug=slug,
        section_number=photo.section_number,
        daily_report_id=photo.daily_report_id,
        user_id=photo.user_id,
        username=photo.user.username if photo.user else None,
        filename=photo.filename,
        view_url=_photo_view_url(slug, photo.id),
        annotated_url=_photo_annotated_url(slug, photo.id) if photo.annotated_path else None,
        content_type=photo.content_type,
        sha256=photo.sha256,
        width=photo.width,
        height=photo.height,
        taken_at=photo.taken_at,
        geo_lat=photo.geo_lat,
        geo_lng=photo.geo_lng,
        caption=photo.caption,
        created_at=photo.created_at,
    )


def _extract_exif(data: bytes) -> dict:
    """Try to extract taken_at + GPS from EXIF; tolerate missing PIL."""
    try:
        from io import BytesIO

        from PIL import ExifTags, Image

        image = Image.open(BytesIO(data))
        width, height = image.size
        exif = image._getexif() or {}  # type: ignore[attr-defined]
        tag_map = {ExifTags.TAGS.get(tag, tag): value for tag, value in exif.items()}
        result: dict = {"width": width, "height": height}

        date_str = tag_map.get("DateTimeOriginal") or tag_map.get("DateTime")
        if date_str:
            for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    result["taken_at"] = datetime.strptime(str(date_str), fmt)
                    break
                except ValueError:
                    continue

        gps = tag_map.get("GPSInfo")
        if gps:
            gps_tags = {ExifTags.GPSTAGS.get(t, t): v for t, v in gps.items()}
            lat = _gps_to_decimal(gps_tags.get("GPSLatitude"), gps_tags.get("GPSLatitudeRef"))
            lng = _gps_to_decimal(gps_tags.get("GPSLongitude"), gps_tags.get("GPSLongitudeRef"))
            if lat is not None:
                result["geo_lat"] = lat
            if lng is not None:
                result["geo_lng"] = lng

        return result
    except Exception:
        return {}


def _gps_to_decimal(coord, ref) -> float | None:
    if not coord:
        return None
    try:
        degrees, minutes, seconds = [float(part) for part in coord]
        decimal = degrees + minutes / 60.0 + seconds / 3600.0
        if ref and str(ref).upper() in ("S", "W"):
            decimal = -decimal
        return decimal
    except Exception:
        return None


@router.post("/projects/{slug}/photos", response_model=ProjectPhotoRead)
async def upload_photo(
    slug: str,
    file: UploadFile = File(...),
    section_number: int | None = Form(None),
    daily_report_id: int | None = Form(None),
    caption: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectPhotoRead:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    suffix = _safe_extension(file.filename or "photo", ALLOWED_PHOTO_EXTENSIONS)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload")

    digest = _sha256(data)
    safe_name = f"{digest[:12]}{suffix}"

    photos_dir = settings.uploads_path / "photos" / slug
    photos_dir.mkdir(parents=True, exist_ok=True)
    target = photos_dir / safe_name
    target.write_bytes(data)

    exif = _extract_exif(data)
    photo = ProjectPhoto(
        project_id=project.id,
        section_number=section_number,
        daily_report_id=daily_report_id,
        user_id=current_user.id,
        filename=Path(file.filename or safe_name).name,
        path=str(target),
        content_type=file.content_type,
        sha256=digest,
        width=exif.get("width"),
        height=exif.get("height"),
        taken_at=exif.get("taken_at"),
        geo_lat=exif.get("geo_lat"),
        geo_lng=exif.get("geo_lng"),
        caption=caption,
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return _photo_to_read(photo, slug)


@router.post("/projects/{slug}/photos/{photo_id}/annotation", response_model=ProjectPhotoRead)
async def upload_annotation(
    slug: str,
    photo_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectPhotoRead:
    """Upload an annotated overlay or composite for a photo (PNG)."""
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    photo = (
        db.query(ProjectPhoto)
        .filter(ProjectPhoto.id == photo_id, ProjectPhoto.project_id == project.id)
        .one_or_none()
    )
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")

    suffix = _safe_extension(file.filename or "annotation.png", {".png"})
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty annotation upload")

    photos_dir = settings.uploads_path / "photos" / slug
    photos_dir.mkdir(parents=True, exist_ok=True)
    target = photos_dir / f"{photo.sha256[:12]}.annotated{suffix}"
    target.write_bytes(data)

    photo.annotated_path = str(target)
    db.commit()
    db.refresh(photo)
    return _photo_to_read(photo, slug)


@router.get("/projects/{slug}/photos", response_model=list[ProjectPhotoRead])
def list_photos(
    slug: str,
    section_number: int | None = None,
    daily_report_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProjectPhotoRead]:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    query = (
        db.query(ProjectPhoto)
        .options(selectinload(ProjectPhoto.user))
        .filter(ProjectPhoto.project_id == project.id)
    )
    if section_number is not None:
        query = query.filter(ProjectPhoto.section_number == section_number)
    if daily_report_id is not None:
        query = query.filter(ProjectPhoto.daily_report_id == daily_report_id)
    photos = query.order_by(ProjectPhoto.created_at.desc()).all()
    return [_photo_to_read(photo, slug) for photo in photos]


@router.get("/projects/{slug}/photos/{photo_id}/raw")
def get_photo_raw(
    slug: str,
    photo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    photo = (
        db.query(ProjectPhoto)
        .filter(ProjectPhoto.id == photo_id, ProjectPhoto.project_id == project.id)
        .one_or_none()
    )
    if photo is None or not Path(photo.path).exists():
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(photo.path, media_type=photo.content_type or "image/jpeg")


@router.get("/projects/{slug}/photos/{photo_id}/annotated")
def get_photo_annotated(
    slug: str,
    photo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    photo = (
        db.query(ProjectPhoto)
        .filter(ProjectPhoto.id == photo_id, ProjectPhoto.project_id == project.id)
        .one_or_none()
    )
    if photo is None or not photo.annotated_path or not Path(photo.annotated_path).exists():
        raise HTTPException(status_code=404, detail="Annotation not found")
    return FileResponse(photo.annotated_path, media_type="image/png")


@router.patch("/projects/{slug}/photos/{photo_id}", response_model=ProjectPhotoRead)
def update_photo(
    slug: str,
    photo_id: int,
    payload: ProjectPhotoUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectPhotoRead:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    photo = (
        db.query(ProjectPhoto)
        .filter(ProjectPhoto.id == photo_id, ProjectPhoto.project_id == project.id)
        .one_or_none()
    )
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")

    if payload.caption is not None:
        photo.caption = payload.caption
    if payload.section_number is not None:
        photo.section_number = payload.section_number
    if payload.daily_report_id is not None:
        photo.daily_report_id = payload.daily_report_id
    db.commit()
    db.refresh(photo)
    return _photo_to_read(photo, slug)


@router.delete("/projects/{slug}/photos/{photo_id}", status_code=204)
def delete_photo(
    slug: str,
    photo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    photo = (
        db.query(ProjectPhoto)
        .filter(ProjectPhoto.id == photo_id, ProjectPhoto.project_id == project.id)
        .one_or_none()
    )
    if photo is None:
        return
    for candidate in (photo.path, photo.annotated_path):
        if candidate and Path(candidate).exists():
            try:
                Path(candidate).unlink()
            except OSError:
                pass
    db.delete(photo)
    db.commit()


# ---------------------------------------------------------------------------
# Voice notes
# ---------------------------------------------------------------------------


def _voice_audio_url(slug: str, voice_id: int) -> str:
    return f"/api/projects/{slug}/voice-notes/{voice_id}/audio"


def _voice_to_read(note: VoiceNote, slug: str) -> VoiceNoteRead:
    return VoiceNoteRead(
        id=note.id,
        project_slug=slug,
        user_id=note.user_id,
        username=note.user.username if note.user else None,
        audio_url=_voice_audio_url(slug, note.id),
        content_type=note.content_type,
        duration_seconds=note.duration_seconds,
        intent=note.intent,
        transcript=note.transcript,
        transcript_provider=note.transcript_provider,
        transcript_language=note.transcript_language,
        transcription_status=note.transcription_status,
        transcription_error=note.transcription_error,
        created_at=note.created_at,
        transcribed_at=note.transcribed_at,
    )


@router.post("/projects/{slug}/voice-notes", response_model=VoiceNoteRead)
async def upload_voice_note(
    slug: str,
    file: UploadFile = File(...),
    intent: str = Form("freitext"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VoiceNoteRead:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    if intent not in ("daily_report", "ibn", "uebergabe", "freitext"):
        raise HTTPException(status_code=400, detail="Unsupported intent")

    suffix = _safe_extension(file.filename or "voice", ALLOWED_AUDIO_EXTENSIONS)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio upload")

    digest = _sha256(data)
    audio_dir = settings.uploads_path / "voice" / slug
    audio_dir.mkdir(parents=True, exist_ok=True)
    target = audio_dir / f"{digest[:12]}{suffix}"
    target.write_bytes(data)

    note = VoiceNote(
        project_id=project.id,
        user_id=current_user.id,
        audio_path=str(target),
        content_type=file.content_type,
        intent=intent,
        transcription_status="pending",
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    # Transkription wird in 13.2 vom Whisper-Agent angestossen; hier nur Persistenz.
    return _voice_to_read(note, slug)


@router.get("/projects/{slug}/voice-notes", response_model=list[VoiceNoteRead])
def list_voice_notes(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[VoiceNoteRead]:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    notes = (
        db.query(VoiceNote)
        .options(selectinload(VoiceNote.user))
        .filter(VoiceNote.project_id == project.id)
        .order_by(VoiceNote.created_at.desc())
        .all()
    )
    return [_voice_to_read(note, slug) for note in notes]


@router.get("/projects/{slug}/voice-notes/{voice_id}/audio")
def get_voice_audio(
    slug: str,
    voice_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    note = (
        db.query(VoiceNote)
        .filter(VoiceNote.id == voice_id, VoiceNote.project_id == project.id)
        .one_or_none()
    )
    if note is None or not Path(note.audio_path).exists():
        raise HTTPException(status_code=404, detail="Voice note not found")
    return FileResponse(note.audio_path, media_type=note.content_type or "audio/webm")


@router.patch("/projects/{slug}/voice-notes/{voice_id}", response_model=VoiceNoteRead)
def update_voice_note(
    slug: str,
    voice_id: int,
    payload: VoiceNoteUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VoiceNoteRead:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    note = (
        db.query(VoiceNote)
        .filter(VoiceNote.id == voice_id, VoiceNote.project_id == project.id)
        .one_or_none()
    )
    if note is None:
        raise HTTPException(status_code=404, detail="Voice note not found")

    if payload.transcript is not None:
        note.transcript = payload.transcript
        note.transcription_status = "ok"
        note.transcript_provider = note.transcript_provider or "manual"
    if payload.intent is not None:
        note.intent = payload.intent
    db.commit()
    db.refresh(note)
    return _voice_to_read(note, slug)


@router.delete("/projects/{slug}/voice-notes/{voice_id}", status_code=204)
def delete_voice_note(
    slug: str,
    voice_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    note = (
        db.query(VoiceNote)
        .filter(VoiceNote.id == voice_id, VoiceNote.project_id == project.id)
        .one_or_none()
    )
    if note is None:
        return
    if Path(note.audio_path).exists():
        try:
            Path(note.audio_path).unlink()
        except OSError:
            pass
    db.delete(note)
    db.commit()
