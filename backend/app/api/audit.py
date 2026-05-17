from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.orm_models import AuditEvent, User
from app.models.audit import AuditEventRead
from app.services.audit_log import set_audit_user
from app.services.auth import ADMIN_ROLES, get_current_user, require_global_role

router = APIRouter()


def _to_event_read(row: AuditEvent) -> AuditEventRead:
    return AuditEventRead(
        id=row.id,
        user_id=row.user_id,
        action=row.action,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        project_slug=row.project_slug,
        changes_json=row.changes_json,
        ip_address=row.ip_address,
        user_agent=row.user_agent,
        created_at=row.created_at,
    )


@router.get("/events", response_model=list[AuditEventRead])
def list_audit_events(
    entity_type: str | None = Query(default=None),
    project_slug: str | None = Query(default=None),
    action: str | None = Query(default=None),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AuditEventRead]:
    require_global_role(current_user, ADMIN_ROLES)
    set_audit_user(current_user.id)

    query = db.query(AuditEvent)
    if entity_type:
        query = query.filter(AuditEvent.entity_type == entity_type)
    if project_slug:
        query = query.filter(AuditEvent.project_slug == project_slug)
    if action:
        query = query.filter(AuditEvent.action == action)
    if from_ is not None:
        query = query.filter(AuditEvent.created_at >= from_)
    if to is not None:
        query = query.filter(AuditEvent.created_at <= to)

    rows = query.order_by(AuditEvent.created_at.desc()).limit(limit).all()
    return [_to_event_read(row) for row in rows]
