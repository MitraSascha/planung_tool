from datetime import datetime

from pydantic import BaseModel, Field


class ProjectPhotoRead(BaseModel):
    id: int
    project_slug: str
    section_number: int | None = None
    daily_report_id: int | None = None
    user_id: int | None = None
    username: str | None = None
    filename: str
    view_url: str
    annotated_url: str | None = None
    content_type: str | None = None
    sha256: str
    width: int | None = None
    height: int | None = None
    taken_at: datetime | None = None
    geo_lat: float | None = None
    geo_lng: float | None = None
    caption: str | None = None
    created_at: datetime


class ProjectPhotoUpdate(BaseModel):
    caption: str | None = None
    section_number: int | None = None
    daily_report_id: int | None = None


class VoiceNoteRead(BaseModel):
    id: int
    project_slug: str
    user_id: int | None = None
    username: str | None = None
    audio_url: str
    content_type: str | None = None
    duration_seconds: float | None = None
    intent: str
    transcript: str | None = None
    transcript_provider: str | None = None
    transcript_language: str | None = None
    transcription_status: str
    transcription_error: str | None = None
    created_at: datetime
    transcribed_at: datetime | None = None


class VoiceNoteUpdate(BaseModel):
    transcript: str | None = None
    intent: str | None = Field(default=None, pattern="^(daily_report|ibn|uebergabe|freitext)$")


class GenerateWithExtrasRequest(BaseModel):
    """Payload mit voice_note_id-Liste: das Backend baut die Transkripte in
    input.json ein und ruft dann den Generator wie gewohnt auf."""

    voice_note_ids: list[int] = Field(default_factory=list)
