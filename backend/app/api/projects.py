import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.settings import settings
from app.db.database import get_db
from app.db.orm_models import GenerationRun, Project, ProjectSection, ProjectUpload
from app.models.project import (
    GenerateRequest,
    GenerateResponse,
    ProjectCreate,
    ProjectRead,
    ProjectUploadRead,
    ProjectWorkspace,
    PublishResponse,
)
from app.services.codex_runner import build_generation_prompt, run_codex
from app.services.project_workspace import create_project_workspace, publish_project

router = APIRouter()


def _preview_url(slug: str) -> str:
    return f"https://{slug}.{settings.public_base_domain}"


def _to_project_read(project: Project) -> ProjectRead:
    return ProjectRead(
        slug=project.slug,
        name=project.name,
        address=project.address,
        responsible=project.responsible,
        construction_manager=project.construction_manager,
        foreman=project.foreman,
        planned_start=project.planned_start,
        planned_end=project.planned_end,
        notes=project.notes,
        sections=[
            {
                "number": section.number,
                "name": section.name,
                "goal": section.goal,
                "planned_hours": section.planned_hours,
                "responsible": section.responsible,
                "staff": section.staff,
            }
            for section in project.sections
        ],
        status=project.status,
        preview_url=_preview_url(project.slug),
    )


@router.post("", response_model=ProjectWorkspace)
def create_project(project: ProjectCreate, db: Session = Depends(get_db)) -> ProjectWorkspace:
    if not project.sections:
        raise HTTPException(status_code=400, detail="At least one section is required")

    db_project = Project(
        slug=project.slug,
        name=project.name,
        address=project.address,
        responsible=project.responsible,
        construction_manager=project.construction_manager,
        foreman=project.foreman,
        planned_start=project.planned_start,
        planned_end=project.planned_end,
        notes=project.notes,
        sections=[
            ProjectSection(
                number=section.number,
                name=section.name,
                goal=section.goal,
                planned_hours=section.planned_hours,
                responsible=section.responsible,
                staff=section.staff,
            )
            for section in project.sections
        ],
    )
    db.add(db_project)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Project slug already exists") from exc

    return create_project_workspace(project)


@router.get("", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)) -> list[ProjectRead]:
    projects = db.query(Project).options(selectinload(Project.sections)).order_by(Project.created_at.desc()).all()
    return [_to_project_read(project) for project in projects]


@router.get("/{slug}", response_model=ProjectRead)
def get_project(slug: str, db: Session = Depends(get_db)) -> ProjectRead:
    project = (
        db.query(Project)
        .options(selectinload(Project.sections))
        .filter(Project.slug == slug)
        .one_or_none()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return _to_project_read(project)


@router.post("/{slug}/uploads", response_model=ProjectUploadRead)
def upload_project_file(
    slug: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ProjectUploadRead:
    project = db.query(Project).filter(Project.slug == slug).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    workspace_docs = settings.workspaces_path / slug / "docs"
    workspace_docs.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename or "upload.bin").name
    target_path = workspace_docs / safe_name

    with target_path.open("wb") as target:
        shutil.copyfileobj(file.file, target)

    upload = ProjectUpload(
        project_id=project.id,
        filename=safe_name,
        path=str(target_path),
        content_type=file.content_type,
    )
    db.add(upload)
    db.commit()

    return ProjectUploadRead(
        filename=safe_name,
        path=str(target_path),
        content_type=file.content_type,
    )


@router.post("/{slug}/generate", response_model=GenerateResponse)
def generate_project(
    slug: str,
    request: GenerateRequest,
    db: Session = Depends(get_db),
) -> GenerateResponse:
    project = db.query(Project).filter(Project.slug == slug).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    workspace_path = settings.workspaces_path / slug
    input_path = workspace_path / "input.json"

    if not input_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Project workspace not found. Create the project before starting generation.",
        )

    prompt = build_generation_prompt(request.prompt)
    command = [
        "codex",
        "exec",
        "-p",
        settings.codex_profile,
        "--cd",
        str(workspace_path),
        "--skip-git-repo-check",
        "-",
    ]

    if not request.run_codex:
        return GenerateResponse(
            slug=slug,
            command=command,
            returncode=None,
            stdout="Dry run only. Set run_codex=true to execute Codex.",
            stderr=prompt,
        )

    generation_run = GenerationRun(
        project_id=project.id,
        status="running",
        codex_profile=settings.codex_profile,
        prompt=prompt,
    )
    db.add(generation_run)
    db.commit()

    result = run_codex(str(workspace_path), prompt)
    generation_run.returncode = result.returncode
    generation_run.stdout = result.stdout
    generation_run.stderr = result.stderr
    generation_run.finished_at = datetime.now(timezone.utc)
    generation_run.status = "succeeded" if result.returncode == 0 else "failed"
    project.status = "generated" if result.returncode == 0 else "generation_failed"

    if result.returncode == 0:
        try:
            publish_project(slug, expected_section_count=len(project.sections))
            project.status = "published"
        except (FileNotFoundError, ValueError) as exc:
            generation_run.status = "publish_failed"
            project.status = "publish_failed"
            db.commit()
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    db.commit()

    return GenerateResponse(
        slug=slug,
        command=command,
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


@router.post("/{slug}/publish", response_model=PublishResponse)
def publish_existing_project(slug: str, db: Session = Depends(get_db)) -> PublishResponse:
    project = db.query(Project).filter(Project.slug == slug).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        published_path = publish_project(slug, expected_section_count=len(project.sections))
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    project.status = "published"
    db.commit()

    return PublishResponse(
        slug=slug,
        published_path=str(published_path),
        preview_url=_preview_url(slug),
    )
