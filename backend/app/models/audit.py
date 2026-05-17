from datetime import datetime

from pydantic import BaseModel


class AuditEventRead(BaseModel):
    id: int
    user_id: int | None = None
    action: str
    entity_type: str
    entity_id: str | None = None
    project_slug: str | None = None
    changes_json: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime
