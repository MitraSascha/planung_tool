from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.orm_models import Project, User
from app.models.dsgvo import (
    AnonymizeResponse,
    CleanupResponse,
    DeleteProjectRequest,
    DeleteResponse,
    RetentionRuleRead,
    RetentionRuleUpsert,
)
from app.services import dsgvo_workflow, retention
from app.services.audit_log import set_audit_user
from app.services.auth import ADMIN_ROLES, get_current_user, require_global_role

router = APIRouter()


def _project_or_404(db: Session, slug: str) -> Project:
    project = db.query(Project).filter(Project.slug == slug).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _to_rule_read(rule) -> RetentionRuleRead:
    return RetentionRuleRead(
        id=rule.id,
        entity_type=rule.entity_type,
        ttl_days=rule.ttl_days,
        action=rule.action,
        enabled=rule.enabled,
        description=rule.description,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


# ---------------------------------------------------------------------------
# Projekt-Anonymisierung / Hard-Delete
# ---------------------------------------------------------------------------


@router.post("/projects/{slug}/anonymize", response_model=AnonymizeResponse)
def anonymize_project_endpoint(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnonymizeResponse:
    require_global_role(current_user, ADMIN_ROLES)
    set_audit_user(current_user.id)

    project = _project_or_404(db, slug)
    stats = dsgvo_workflow.anonymize_project(db, project, current_user)
    return AnonymizeResponse(
        slug=slug,
        updated_rows=stats.get("updated_rows", 0),
        errors=stats.get("errors", []),
    )


@router.post("/projects/{slug}/delete", response_model=DeleteResponse)
def delete_project_endpoint(
    slug: str,
    request: DeleteProjectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeleteResponse:
    require_global_role(current_user, ADMIN_ROLES)
    set_audit_user(current_user.id)

    expected = f"DELETE-{slug}"
    if request.confirm != expected:
        raise HTTPException(
            status_code=400,
            detail=f"Confirmation token must equal '{expected}'",
        )

    project = _project_or_404(db, slug)
    result = dsgvo_workflow.delete_project_data(db, project, current_user)
    return DeleteResponse(
        slug=slug,
        deleted_project_id=result["deleted_project_id"],
        removed_files=result["removed_files"],
        removed_dirs=result["removed_dirs"],
    )


# ---------------------------------------------------------------------------
# Retention Rules
# ---------------------------------------------------------------------------


@router.get("/retention-rules", response_model=list[RetentionRuleRead])
def list_retention_rules_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RetentionRuleRead]:
    require_global_role(current_user, ADMIN_ROLES)
    set_audit_user(current_user.id)
    return [_to_rule_read(rule) for rule in retention.list_retention_rules(db)]


@router.put("/retention-rules", response_model=RetentionRuleRead)
def upsert_retention_rule_endpoint(
    payload: RetentionRuleUpsert,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RetentionRuleRead:
    require_global_role(current_user, ADMIN_ROLES)
    set_audit_user(current_user.id)
    try:
        rule = retention.upsert_retention_rule(db, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_rule_read(rule)


@router.delete("/retention-rules/{entity_type}")
def delete_retention_rule_endpoint(
    entity_type: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    require_global_role(current_user, ADMIN_ROLES)
    set_audit_user(current_user.id)
    removed = retention.delete_retention_rule(db, entity_type)
    if not removed:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"deleted": entity_type}


@router.post("/retention-rules/cleanup", response_model=CleanupResponse)
def run_cleanup_endpoint(
    dry_run: bool = Query(default=True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CleanupResponse:
    require_global_role(current_user, ADMIN_ROLES)
    set_audit_user(current_user.id)
    result = retention.run_retention_cleanup(db, dry_run=dry_run)
    return CleanupResponse(**result)
