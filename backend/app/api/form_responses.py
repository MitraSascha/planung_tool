"""Persistence for fields filled in generated HTML documents.

The generator emits HTML with stable ``data-field-id="<role>.<doc>.<...>"``
attributes on every fillable element. The browser snippet
(see ``backend/app/api/projects.py::_inject_form_sync_script``) POSTs
each change here; project leads later aggregate across users to see
overall progress and flagged issues.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
from app.db.orm_models import FormResponse, Project, User
from app.models.forms import (
    DocumentResponses,
    FormResponseRead,
    FormResponseWrite,
    ProjectResponsesAggregate,
)
from app.services.auth import (
    PROJECT_READ_ROLES,
    SITE_LEAD_ROLES,
    get_current_user,
    require_project_role,
)

router = APIRouter()


def _project_or_404(db: Session, slug: str) -> Project:
    project = db.query(Project).filter(Project.slug == slug).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _row_to_read(row: FormResponse, slug: str) -> FormResponseRead:
    return FormResponseRead(
        field_id=row.field_id,
        value_type=row.value_type,  # type: ignore[arg-type]
        value_bool=row.value_bool,
        value_text=row.value_text,
        value_number=row.value_number,
        value_date=row.value_date,
        project_slug=slug,
        document_path=row.document_path,
        filled_by_user_id=row.filled_by_user_id,
        filled_by_username=row.filled_by.username if row.filled_by else None,
        filled_at=row.filled_at,
        updated_at=row.updated_at,
    )


@router.get(
    "/{slug}/form-responses/{document_path:path}",
    response_model=DocumentResponses,
)
def get_my_responses_for_document(
    slug: str,
    document_path: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentResponses:
    """Return the current user's own answers for one document.

    Used by the in-page JS snippet at load time to pre-fill what the
    monteur entered last time. Other users' answers are *not* exposed
    here so individual reports stay individual.
    """
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    rows = (
        db.query(FormResponse)
        .options(joinedload(FormResponse.filled_by))
        .filter(
            FormResponse.project_id == project.id,
            FormResponse.document_path == document_path,
            FormResponse.filled_by_user_id == current_user.id,
        )
        .all()
    )
    return DocumentResponses(
        project_slug=slug,
        document_path=document_path,
        responses=[_row_to_read(r, slug) for r in rows],
    )


@router.put(
    "/{slug}/form-responses/{document_path:path}",
    response_model=FormResponseRead,
)
def upsert_form_response(
    slug: str,
    document_path: str,
    payload: FormResponseWrite,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FormResponseRead:
    """Create or update one field's value for the current user.

    PUT (not POST) because the operation is idempotent on
    (project, document, field, user). The unique constraint enforces
    one row per user per field — repeated calls overwrite.
    """
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    row = (
        db.query(FormResponse)
        .filter(
            FormResponse.project_id == project.id,
            FormResponse.document_path == document_path,
            FormResponse.field_id == payload.field_id,
            FormResponse.filled_by_user_id == current_user.id,
        )
        .one_or_none()
    )
    if row is None:
        row = FormResponse(
            project_id=project.id,
            document_path=document_path,
            field_id=payload.field_id,
            filled_by_user_id=current_user.id,
        )
        db.add(row)

    row.value_type = payload.value_type
    row.value_bool = payload.value_bool
    row.value_text = payload.value_text
    row.value_number = payload.value_number
    row.value_date = payload.value_date

    db.commit()
    db.refresh(row)
    # Wenn die Antwort eine Checklist-Position betrifft, Meilensteine
    # neu durchrechnen (Druckprüfung / Abschnitts-Abschluss / Inbetriebnahme).
    if payload.field_id.startswith("checkliste."):
        from app.services.milestones import sync_milestones
        try:
            sync_milestones(db, project.id)
        except Exception:
            # Meilensteine sind sekundär — Hauptantwort darf nicht scheitern.
            db.rollback()
    # joinedload would have been cleaner, but the refresh already fetched
    # the row — load filled_by lazily on the way out.
    _ = row.filled_by
    return _row_to_read(row, slug)


@router.delete(
    "/{slug}/form-responses/{document_path:path}/field/{field_id}",
    status_code=204,
)
def delete_form_response(
    slug: str,
    document_path: str,
    field_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Remove the current user's answer for a single field."""
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    row = (
        db.query(FormResponse)
        .filter(
            FormResponse.project_id == project.id,
            FormResponse.document_path == document_path,
            FormResponse.field_id == field_id,
            FormResponse.filled_by_user_id == current_user.id,
        )
        .one_or_none()
    )
    if row is None:
        return
    db.delete(row)
    db.commit()


@router.get(
    "/{slug}/form-responses",
    response_model=ProjectResponsesAggregate,
)
def get_project_responses_aggregate(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectResponsesAggregate:
    """Aggregate every user's responses for a project, grouped by document.

    Restricted to site-lead roles — this is the dashboard data the
    project lead uses to see overall progress and flagged issues.
    """
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)

    rows = (
        db.query(FormResponse)
        .options(joinedload(FormResponse.filled_by))
        .filter(FormResponse.project_id == project.id)
        .order_by(FormResponse.document_path, FormResponse.field_id)
        .all()
    )
    by_doc: dict[str, list[FormResponseRead]] = {}
    for row in rows:
        by_doc.setdefault(row.document_path, []).append(_row_to_read(row, slug))

    return ProjectResponsesAggregate(
        project_slug=slug,
        documents=[
            DocumentResponses(
                project_slug=slug,
                document_path=doc,
                responses=responses,
            )
            for doc, responses in by_doc.items()
        ],
    )
