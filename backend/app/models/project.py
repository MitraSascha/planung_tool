from pydantic import BaseModel, Field

SLUG_PATTERN = r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"


class ProjectSection(BaseModel):
    number: int
    name: str
    goal: str | None = None
    planned_hours: float | None = None
    responsible: str | None = None
    staff: str | None = None


class ProjectCreate(BaseModel):
    slug: str = Field(pattern=SLUG_PATTERN)
    name: str
    address: str | None = None
    responsible: str | None = None
    construction_manager: str | None = None
    foreman: str | None = None
    planned_start: str | None = None
    planned_end: str | None = None
    sections: list[ProjectSection]
    notes: str | None = None


class ProjectWorkspace(BaseModel):
    slug: str
    workspace_path: str
    input_path: str
    output_path: str
    preview_url: str


class ProjectRead(ProjectCreate):
    status: str
    preview_url: str


class ProjectUploadRead(BaseModel):
    filename: str
    path: str
    content_type: str | None = None


class PublishResponse(BaseModel):
    slug: str
    published_path: str
    preview_url: str


class GenerateRequest(BaseModel):
    run_codex: bool = False
    prompt: str | None = None


class GenerateResponse(BaseModel):
    slug: str
    command: list[str]
    returncode: int | None
    stdout: str
    stderr: str
