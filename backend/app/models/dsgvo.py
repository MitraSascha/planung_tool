from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AnonymizeResponse(BaseModel):
    slug: str
    updated_rows: int
    errors: list[str] = Field(default_factory=list)


class DeleteProjectRequest(BaseModel):
    confirm: str


class DeleteResponse(BaseModel):
    slug: str
    deleted_project_id: int
    removed_files: int
    removed_dirs: int


class RetentionRuleRead(BaseModel):
    id: int
    entity_type: str
    ttl_days: int
    action: str
    enabled: bool
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class RetentionRuleUpsert(BaseModel):
    entity_type: str
    ttl_days: int = Field(ge=0)
    action: str = Field(pattern="^(delete|anonymize)$", default="delete")
    enabled: bool = True
    description: str | None = None


class CleanupResponse(BaseModel):
    dry_run: bool
    rules: dict[str, Any]
