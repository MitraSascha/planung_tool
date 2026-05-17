"""HTTP endpoints for managing and rendering document templates.

Read endpoints are open to any authenticated user; the (future) write
endpoints will be gated to ADMIN_ROLES. The Admin-Panel editor (see backlog)
will plug into these.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.orm_models import User
from app.services import template_renderer
from app.services.auth import (
    ADMIN_ROLES,
    get_current_user,
    get_current_user_query_or_header,
    require_global_role,
)


router = APIRouter()


class TemplateSummary(BaseModel):
    slug: str
    category: str
    title: str
    description: str | None
    version: int

    @classmethod
    def from_row(cls, row) -> "TemplateSummary":
        return cls(
            slug=row.slug,
            category=row.category,
            title=row.title,
            description=row.description,
            version=row.version,
        )


class TemplateDetail(TemplateSummary):
    html_template: str
    data_schema: str | None

    @classmethod
    def from_row(cls, row) -> "TemplateDetail":  # type: ignore[override]
        return cls(
            slug=row.slug,
            category=row.category,
            title=row.title,
            description=row.description,
            version=row.version,
            html_template=row.html_template,
            data_schema=row.data_schema,
        )


@router.get("", response_model=list[TemplateSummary])
def list_templates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TemplateSummary]:
    rows = template_renderer.list_templates(db)
    return [TemplateSummary.from_row(r) for r in rows]


@router.get("/{slug}", response_model=TemplateDetail)
def get_template(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TemplateDetail:
    require_global_role(current_user, ADMIN_ROLES)
    try:
        row = template_renderer.get_template(db, slug)
    except template_renderer.TemplateNotFoundError:
        raise HTTPException(status_code=404, detail="Template not found")
    return TemplateDetail.from_row(row)


@router.get("/{slug}/preview", response_class=HTMLResponse)
def preview_template(
    slug: str,
    current_user: User = Depends(get_current_user_query_or_header),
    db: Session = Depends(get_db),
) -> Response:
    """Render the template with empty/sample data — no project context
    required. Browser-navigable (token via ?token=), so an admin can
    open the link in a new tab directly from the Admin-Panel later."""
    try:
        result = template_renderer.render_preview(db, slug)
    except template_renderer.TemplateNotFoundError:
        raise HTTPException(status_code=404, detail="Template not found")
    return HTMLResponse(content=result.html)


@router.get("/{slug}/render/{project_slug}", response_class=HTMLResponse)
def render_for_project(
    slug: str,
    project_slug: str,
    current_user: User = Depends(get_current_user_query_or_header),
    db: Session = Depends(get_db),
) -> Response:
    try:
        result = template_renderer.render(db, slug, project_slug)
    except template_renderer.TemplateNotFoundError:
        raise HTTPException(status_code=404, detail="Template not found")
    except template_renderer.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
    return HTMLResponse(content=result.html)
