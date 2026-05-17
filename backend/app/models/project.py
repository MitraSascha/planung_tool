from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

SLUG_PATTERN = r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"


def _empty_to_none(value: Any) -> Any:
    """Coerce blank-ish form values to None so optional date fields don't 422."""
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


class UserBrief(BaseModel):
    id: int
    username: str
    display_name: str


class ProjectSection(BaseModel):
    number: int
    name: str
    goal: str | None = None
    planned_hours: float | None = None
    responsible: str | None = None
    staff: str | None = None
    staff_user_ids: list[int] = Field(default_factory=list)
    staff_users: list[UserBrief] = Field(default_factory=list)

    @field_validator("planned_hours", mode="before")
    @classmethod
    def _coerce_blank_hours(cls, v: Any) -> Any:
        return _empty_to_none(v)


class ProjectCreate(BaseModel):
    slug: str = Field(pattern=SLUG_PATTERN)
    name: str
    project_type: str = "standard"
    address: str | None = None
    client_name: str | None = None
    responsible: str | None = None
    construction_manager: str | None = None
    foreman: str | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    sections: list[ProjectSection]
    notes: str | None = None

    @field_validator("planned_start", "planned_end", mode="before")
    @classmethod
    def _coerce_blank_dates(cls, v: Any) -> Any:
        return _empty_to_none(v)


class ProjectUpdate(BaseModel):
    name: str
    project_type: str = "standard"
    address: str | None = None
    client_name: str | None = None
    responsible: str | None = None
    construction_manager: str | None = None
    foreman: str | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    sections: list[ProjectSection]
    notes: str | None = None

    @field_validator("planned_start", "planned_end", mode="before")
    @classmethod
    def _coerce_blank_dates(cls, v: Any) -> Any:
        return _empty_to_none(v)


class ProjectWorkspace(BaseModel):
    slug: str
    workspace_path: str
    input_path: str
    output_path: str
    preview_url: str | None = None


class ProjectUploadRead(BaseModel):
    filename: str
    path: str
    content_type: str | None = None
    size_bytes: int | None = None
    created_at: datetime | None = None


class ProjectRead(ProjectCreate):
    status: str
    preview_url: str | None = None
    uploads: list[ProjectUploadRead] = Field(default_factory=list)
    upload_count: int = 0
    ready_for_generation: bool = False
    readiness_issues: list[str] = Field(default_factory=list)
    documentation_checklist: list[str] = Field(default_factory=list)
    planned_outputs: list[str] = Field(default_factory=list)


class PublishResponse(BaseModel):
    slug: str
    published_path: str
    preview_url: str | None = None


class ProjectOutputFile(BaseModel):
    path: str
    filename: str
    extension: str
    size_bytes: int
    view_url: str


class ProjectOutputVersion(BaseModel):
    label: str
    file_count: int
    created_at: datetime | None = None


class ProjectOutputsRead(BaseModel):
    slug: str
    preview_url: str | None = None
    published: bool
    files: list[ProjectOutputFile] = Field(default_factory=list)
    versions: list[ProjectOutputVersion] = Field(default_factory=list)
    visible_folders: list[str] = Field(default_factory=list)


class GenerateRequest(BaseModel):
    run_codex: bool = False
    prompt: str | None = None


class GenerateResponse(BaseModel):
    slug: str
    command: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    run_id: int | None = None
    status: str | None = None
    progress_current: int = 0
    progress_total: int = 1
    current_step: str | None = None


class GenerationRunRead(BaseModel):
    id: int
    slug: str
    status: str
    returncode: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    progress_current: int = 0
    progress_total: int = 1
    current_step: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
