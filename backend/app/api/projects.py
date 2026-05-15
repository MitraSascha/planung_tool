import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.settings import settings
from app.db.database import get_db
from app.db.orm_models import GenerationRun, Project, ProjectSection, ProjectUpload
from app.models.project import (
    GenerateRequest,
    GenerateResponse,
    ProjectCreate,
    ProjectOutputFile,
    ProjectOutputsRead,
    ProjectRead,
    ProjectUploadRead,
    ProjectWorkspace,
    PublishResponse,
)
from app.services.codex_runner import build_generation_prompt, run_codex
from app.services.project_workspace import create_project_workspace, publish_project

router = APIRouter()

ALLOWED_UPLOAD_SUFFIXES = {".csv", ".pdf", ".xlsx", ".xls"}
VISIBLE_OUTPUT_SUFFIXES = {".html", ".md", ".json", ".xlsx-struktur"}
SMALL_PROJECT_OUTPUTS = [
    "01 Projektuebersicht",
    "06 Detaillierter Ablaufplan",
    "08 Monteur Tagescheckliste",
    "10 Tagesbericht App",
    "11 Meilensteinplan",
    "14 Gantt Uebersicht",
    "99 HTML Uebersicht",
]
STANDARD_SHARED_OUTPUTS = [
    "06 Detaillierter Ablaufplan",
    "07 Checklisten SHK",
    "08 Monteur Tagescheckliste",
    "09 Monteur Wochenplan",
    "10 Tagesbericht App",
    "11 Meilensteinplan",
    "12 Material und Werkzeug",
    "13 Risiko und Maengel",
    "14 Gantt Uebersicht",
    "99 HTML Uebersicht",
]


def _preview_url(slug: str) -> str:
    return f"https://{slug}.{settings.public_base_domain}"


def _upload_size(path: str) -> int | None:
    upload_path = Path(path)
    if not upload_path.exists():
        return None
    return upload_path.stat().st_size


def _project_output_root(slug: str) -> Path:
    return settings.projects_path / slug


def _safe_output_path(slug: str, relative_path: str) -> Path:
    output_root = _project_output_root(slug).resolve()
    requested_path = (output_root / relative_path).resolve()

    if output_root != requested_path and output_root not in requested_path.parents:
        raise HTTPException(status_code=400, detail="Invalid output path")

    if not requested_path.exists() or not requested_path.is_file():
        raise HTTPException(status_code=404, detail="Output file not found")

    return requested_path


def _output_extension(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".xlsx-struktur"):
        return ".xlsx-Struktur"
    return path.suffix.lower()


def _list_output_files(slug: str) -> list[ProjectOutputFile]:
    output_root = _project_output_root(slug)
    if not output_root.exists():
        return []

    files: list[ProjectOutputFile] = []
    for path in sorted(item for item in output_root.rglob("*") if item.is_file()):
        extension = _output_extension(path)
        if extension.lower() not in VISIBLE_OUTPUT_SUFFIXES:
            continue

        relative_path = path.relative_to(output_root).as_posix()
        files.append(
            ProjectOutputFile(
                path=relative_path,
                filename=path.name,
                extension=extension,
                size_bytes=path.stat().st_size,
                view_url=f"/api/projects/{slug}/outputs/file/{relative_path}",
            )
        )

    return files


def _to_upload_read(upload: ProjectUpload) -> ProjectUploadRead:
    return ProjectUploadRead(
        filename=upload.filename,
        path=upload.path,
        content_type=upload.content_type,
        size_bytes=_upload_size(upload.path),
        created_at=upload.created_at,
    )


def _readiness_issues(project: Project) -> list[str]:
    issues: list[str] = []
    is_small_project = project.project_type == "small"

    if not project.uploads and not is_small_project:
        issues.append("Mindestens eine technische Unterlage hochladen.")

    if not project.address and not is_small_project:
        issues.append("Adresse ergänzen.")

    if not project.planned_start or not project.planned_end:
        issues.append("Startdatum und Zieltermin ergänzen.")

    sections_without_goal = [section.number for section in project.sections if not section.goal]
    if sections_without_goal:
        section_numbers = ", ".join(str(number) for number in sections_without_goal)
        issues.append(f"Zielbeschreibung für Abschnitt {section_numbers} ergänzen.")

    return issues


def _documentation_checklist(project: Project) -> list[str]:
    if project.project_type == "small":
        return [
            "Projektart und grober Leistungsumfang",
            "Startdatum und Zieltermin fuer Gantt/Meilensteine",
            "Mindestens ein Bauabschnitt oder Arbeitspaket",
            "Optional: Angebot, Skizze, Fotos, Materialliste oder PDF-Unterlagen",
        ]

    return [
        "Technische Unterlagen als CSV, PDF, XLSX oder XLS",
        "Projektadresse, Startdatum und Zieltermin",
        "Bauabschnitte mit Zielbeschreibung",
        "Optional: Plaene, Fotos, Materiallisten, LV und Herstellerdaten",
    ]


def _planned_outputs(project: Project) -> list[str]:
    if project.project_type == "small":
        return SMALL_PROJECT_OUTPUTS

    section_outputs = [
        f"{section.number + 1:02d} Abschnitt {section.number}: {section.name}"
        for section in project.sections
    ]
    return ["01 Projektuebersicht", *section_outputs, *STANDARD_SHARED_OUTPUTS]


def _to_project_read(project: Project) -> ProjectRead:
    uploads = [_to_upload_read(upload) for upload in project.uploads]
    readiness_issues = _readiness_issues(project)

    return ProjectRead(
        slug=project.slug,
        name=project.name,
        project_type=project.project_type,
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
        uploads=uploads,
        upload_count=len(uploads),
        ready_for_generation=len(readiness_issues) == 0,
        readiness_issues=readiness_issues,
        documentation_checklist=_documentation_checklist(project),
        planned_outputs=_planned_outputs(project),
    )


@router.post("", response_model=ProjectWorkspace)
def create_project(project: ProjectCreate, db: Session = Depends(get_db)) -> ProjectWorkspace:
    if not project.sections:
        raise HTTPException(status_code=400, detail="At least one section is required")

    db_project = Project(
        slug=project.slug,
        name=project.name,
        project_type=project.project_type,
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
    projects = (
        db.query(Project)
        .options(selectinload(Project.sections), selectinload(Project.uploads))
        .order_by(Project.created_at.desc())
        .all()
    )
    return [_to_project_read(project) for project in projects]


@router.get("/{slug}", response_model=ProjectRead)
def get_project(slug: str, db: Session = Depends(get_db)) -> ProjectRead:
    project = (
        db.query(Project)
        .options(selectinload(Project.sections), selectinload(Project.uploads))
        .filter(Project.slug == slug)
        .one_or_none()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return _to_project_read(project)


@router.get("/{slug}/outputs", response_model=ProjectOutputsRead)
def list_project_outputs(slug: str, db: Session = Depends(get_db)) -> ProjectOutputsRead:
    project = db.query(Project).filter(Project.slug == slug).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    output_root = _project_output_root(slug)
    return ProjectOutputsRead(
        slug=slug,
        preview_url=_preview_url(slug),
        published=output_root.exists(),
        files=_list_output_files(slug),
    )


@router.get("/{slug}/outputs/file/{relative_path:path}")
def get_project_output_file(slug: str, relative_path: str, db: Session = Depends(get_db)) -> FileResponse:
    project = db.query(Project).filter(Project.slug == slug).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return FileResponse(_safe_output_path(slug, relative_path))


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
    if Path(safe_name).suffix.lower() not in ALLOWED_UPLOAD_SUFFIXES:
        allowed_types = ", ".join(sorted(suffix.lstrip(".").upper() for suffix in ALLOWED_UPLOAD_SUFFIXES))
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {allowed_types}")

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
    db.refresh(upload)

    return _to_upload_read(upload)


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

    prompt = build_generation_prompt(project.project_type, request.prompt)
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
            publish_project(slug, expected_section_count=len(project.sections), project_type=project.project_type)
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
        published_path = publish_project(
            slug,
            expected_section_count=len(project.sections),
            project_type=project.project_type,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    project.status = "published"
    db.commit()

    return PublishResponse(
        slug=slug,
        published_path=str(published_path),
        preview_url=_preview_url(slug),
    )
