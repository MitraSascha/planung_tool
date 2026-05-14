import json
import shutil
from pathlib import Path

from app.core.settings import settings
from app.models.project import ProjectCreate, ProjectWorkspace
from app.services.output_validator import validate_project_output


def create_project_workspace(project: ProjectCreate) -> ProjectWorkspace:
    workspace_path = settings.workspaces_path / project.slug
    output_path = workspace_path / "output"
    docs_path = workspace_path / "docs"

    workspace_path.mkdir(parents=True, exist_ok=True)
    output_path.mkdir(parents=True, exist_ok=True)
    docs_path.mkdir(parents=True, exist_ok=True)

    input_path = workspace_path / "input.json"
    input_path.write_text(
        json.dumps(project.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return ProjectWorkspace(
        slug=project.slug,
        workspace_path=str(workspace_path),
        input_path=str(input_path),
        output_path=str(output_path),
        preview_url=f"https://{project.slug}.{settings.public_base_domain}",
    )


def publish_project(slug: str, expected_section_count: int) -> Path:
    workspace_output = settings.workspaces_path / slug / "output"
    public_project = settings.projects_path / slug

    if not workspace_output.exists():
        raise FileNotFoundError(f"Workspace output does not exist: {workspace_output}")

    validate_project_output(workspace_output, expected_section_count)

    if public_project.exists():
        shutil.rmtree(public_project)

    shutil.copytree(workspace_output, public_project)
    return public_project
