import asyncio
import json
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.settings import settings
from app.db.database import SessionLocal, get_db
from app.db.orm_models import (
    GenerationRun,
    Project,
    ProjectMember,
    ProjectSection,
    ProjectSectionStaff,
    ProjectPhoto,
    ProjectUpload,
    User,
    VoiceNote,
)
from app.models.project import (
    GenerateRequest,
    GenerateResponse,
    GenerationRunRead,
    ProjectCreate,
    ProjectOutputFile,
    ProjectOutputVersion,
    ProjectOutputsRead,
    ProjectRead,
    ProjectUpdate,
    ProjectUploadRead,
    ProjectWorkspace,
    PublishResponse,
    UserBrief,
)
from app.services.generator_runner import (
    get_provider_pool,
)
from app.services.template_publisher import SLUG_TO_FILENAME as SLUG_TO_FILENAME_PREVIEW
from app.services.auth import (
    ADMIN_ROLES,
    PROJECT_READ_ROLES,
    SITE_LEAD_ROLES,
    allowed_output_folders,
    ROLE_OUTPUT_EXCLUSIONS,
    get_current_user,
    get_current_user_query_or_header,
    require_global_role,
    require_project_role,
    resolve_effective_role,
)
from app.services.form_sync_snippet import inject_form_sync_snippet
from app.services.pdf_export import (
    PdfRenderError,
    render_html_string_to_pdf,
    render_html_to_pdf,
)
from app.services.pii_tokenizer import pii_tokenizer
from app.services.privacy_workspace import prepare_sanitized_generator_workspace, sync_generator_output
from app.services import template_publisher
from app.services.project_workspace import (
    copy_photos_to_workspace,
    create_project_workspace,
    publish_project,
    write_heating_design_json,
    write_offers_json,
    write_voice_notes_to_workspace,
)

router = APIRouter()

ALLOWED_UPLOAD_SUFFIXES = {".csv", ".pdf", ".xlsx", ".xls"}
VISIBLE_OUTPUT_SUFFIXES = {".html", ".json", ".xlsx-struktur"}
SMALL_PROJECT_OUTPUTS = [
    "00 Start - Navigation",
    "01 Monteur - Tagescheckliste, Ablaufplan, Baustellenhinweise",
    "04 Projektleitung - Projektuebersicht, Meilensteinplan, Gantt",
    "05 Allgemein - Projektunterlagen, Kontakte",
]
STANDARD_SHARED_OUTPUTS = [
    "00 Start - Navigation und Einstieg",
    "01 Monteur - Tagescheckliste, Wochenplan, Ablaufplan, Baustellenhinweise",
    "02 Obermonteur - Teamstatus, Abschnittsplanung, Checklisten",
    "03 Bauleitung - Detaillierter Ablaufplan, Material, Risiken, Blocker",
    "04 Projektleitung - Projektuebersicht, Meilensteinplan, Gantt, Statusuebersicht",
    "05 Allgemein - Projektunterlagen, Kontakte, Dokumentenindex",
]


def _preview_url(slug: str) -> str | None:
    """Subdomain-Veröffentlichung wurde deaktiviert — Outputs werden nur noch
    innerhalb der App ausgeliefert (mit Role-PII-Filter, kein öffentlicher
    Subdomain-Zugriff). Funktion bleibt für API-Kompatibilität bestehen,
    liefert aber konsistent None."""
    return None


def _upload_size(path: str) -> int | None:
    upload_path = Path(path)
    if not upload_path.exists():
        return None
    return upload_path.stat().st_size


def _project_output_root(slug: str) -> Path:
    return settings.projects_path / slug


def _safe_output_path(
    slug: str,
    relative_path: str,
    allowed_folders: frozenset[str] | None = None,
    excluded_files: frozenset[str] | None = None,
) -> Path:
    output_root = _project_output_root(slug).resolve()
    requested_path = (output_root / relative_path).resolve()

    if output_root != requested_path and output_root not in requested_path.parents:
        raise HTTPException(status_code=400, detail="Invalid output path")

    rel_parts = requested_path.relative_to(output_root).parts
    if allowed_folders is not None:
        if not rel_parts or rel_parts[0] not in allowed_folders:
            raise HTTPException(status_code=403, detail="Access to this output file is not allowed")

    if excluded_files:
        rel_str = requested_path.relative_to(output_root).as_posix()
        if rel_str in excluded_files:
            raise HTTPException(status_code=403, detail="Access to this output file is not allowed")

    if not requested_path.exists() or not requested_path.is_file():
        raise HTTPException(status_code=404, detail="Output file not found")

    return requested_path


def _output_extension(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".xlsx-struktur"):
        return ".xlsx-Struktur"
    return path.suffix.lower()


def _list_output_files(
    slug: str,
    allowed_folders: frozenset[str] | None = None,
    excluded_files: frozenset[str] | None = None,
) -> list[ProjectOutputFile]:
    output_root = _project_output_root(slug)
    if not output_root.exists():
        return []

    files: list[ProjectOutputFile] = []
    for path in sorted(item for item in output_root.rglob("*") if item.is_file()):
        rel_parts = path.relative_to(output_root).parts
        if "_versions" in rel_parts:
            continue

        if allowed_folders is not None:
            if not rel_parts or rel_parts[0] not in allowed_folders:
                continue

        if excluded_files:
            relative_str = path.relative_to(output_root).as_posix()
            if relative_str in excluded_files:
                continue

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


def _list_output_versions(
    slug: str,
    allowed_folders: frozenset[str] | None = None,
) -> list[ProjectOutputVersion]:
    version_root = _project_output_root(slug) / "_versions"
    if not version_root.exists():
        return []

    versions: list[ProjectOutputVersion] = []
    for version_path in sorted((item for item in version_root.iterdir() if item.is_dir()), reverse=True):
        if allowed_folders is None:
            file_count = sum(1 for item in version_path.rglob("*") if item.is_file())
        else:
            file_count = 0
            for item in version_path.rglob("*"):
                if not item.is_file():
                    continue
                rel_parts = item.relative_to(version_path).parts
                if not rel_parts or rel_parts[0] not in allowed_folders:
                    continue
                file_count += 1
        versions.append(
            ProjectOutputVersion(
                label=version_path.name,
                file_count=file_count,
                created_at=datetime.fromtimestamp(version_path.stat().st_mtime, tz=timezone.utc),
            )
        )

    return versions


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

    # Eine "technische Unterlage" kann inzwischen drei Formen haben:
    # 1) Datei-Upload (project_uploads — klassische PDF/CSV/XLSX)
    # 2) Strukturierte Heizlast-Daten (heating_design + circuits)
    # 3) Strukturierte Angebote (offers + items)
    # Wenn mind. eine Quelle Daten liefert, ist das Projekt versorgungsfaehig.
    has_uploads = bool(project.uploads)
    has_heating = (
        project.heating_design is not None
        and bool(project.heating_design.circuits)
    )
    has_offers = bool(project.offers) and any(o.items for o in project.offers)
    if not (has_uploads or has_heating or has_offers) and not is_small_project:
        issues.append(
            "Mindestens eine Datenquelle: Datei-Upload, Heizlast-Import oder Angebot."
        )

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
        return list(SMALL_PROJECT_OUTPUTS)
    return list(STANDARD_SHARED_OUTPUTS)


def _section_to_dict(section: ProjectSection) -> dict:
    staff_user_ids: list[int] = []
    staff_users: list[UserBrief] = []
    for staff_row in section.staff_members:
        staff_user_ids.append(staff_row.user_id)
        if staff_row.user is not None:
            staff_users.append(
                UserBrief(
                    id=staff_row.user.id,
                    username=staff_row.user.username,
                    display_name=staff_row.user.display_name,
                )
            )
    return {
        "number": section.number,
        "name": section.name,
        "goal": section.goal,
        "planned_hours": section.planned_hours,
        "responsible": section.responsible,
        "staff": section.staff,
        "staff_user_ids": staff_user_ids,
        "staff_users": staff_users,
    }


def _reveal_pii_for_role(
    db: Session, role: str, project: Project, text: str | None
) -> str | None:
    """Resolve ``[[PII:...]]`` placeholders inline if the role permits it.

    Mirrors the file-output role gating: SITE_LEAD_ROLES see full clear text,
    monteur sees only the project's own staff names revealed, everyone else
    (viewer / unknown) gets the placeholders verbatim.
    """
    if text is None or text == "":
        return text
    if "[[PII:" not in text:
        return text
    if role in _CLEARTEXT_OUTPUT_ROLES:
        revealed, _ = pii_tokenizer.reidentify_text(db, text)
        return revealed
    if role in _PARTIAL_REVEAL_ROLES:
        revealed, _ = pii_tokenizer.reidentify_text_partial(
            db, text, _project_staff_names(project)
        )
        return revealed
    return text


def _generator_input_summary(project: Project, db: Session | None) -> "GeneratorInputSummary":
    """Konsolidierte Sicht: project_uploads + offers + heating + material + sections + members."""
    from app.models.project import (
        GeneratorInputSummary,
        HeatingDesignSummary,
        OfferSummary,
    )
    from app.db.orm_models import MaterialItem

    upload_count = len(project.uploads) if project.uploads else 0
    offer_position_count = sum(len(o.items or []) for o in (project.offers or []))
    offers = [
        OfferSummary(
            id=o.id,
            supplier_name=o.supplier_name,
            offer_no=o.offer_no,
            offer_date=o.offer_date,
            source_file=o.source_file,
            position_count=len(o.items or []),
            total_net_eur=o.total_net_eur,
            created_at=o.created_at,
        )
        for o in sorted((project.offers or []), key=lambda x: x.created_at or 0, reverse=True)
    ]

    heating = None
    if project.heating_design is not None:
        hd = project.heating_design
        heating = HeatingDesignSummary(
            source=hd.source,
            source_file=hd.source_file,
            circuit_count=len(hd.circuits or []),
            system_type=hd.system_type,
            pump_model=hd.pump_model,
            imported_at=hd.imported_at,
        )

    material_count = 0
    material_with_offer = 0
    if db is not None:
        material_rows = db.query(MaterialItem.offer_item_id).filter(
            MaterialItem.project_id == project.id
        ).all()
        material_count = len(material_rows)
        material_with_offer = sum(1 for (oid,) in material_rows if oid is not None)

    return GeneratorInputSummary(
        upload_count=upload_count,
        offer_count=len(offers),
        offer_position_count=offer_position_count,
        offers=offers,
        heating=heating,
        material_item_count=material_count,
        material_item_with_offer_link=material_with_offer,
        section_count=len(project.sections or []),
        member_count=len(project.members) if hasattr(project, "members") and project.members else 0,
    )


def _to_project_read(
    project: Project,
    db: Session | None = None,
    role: str | None = None,
) -> ProjectRead:
    uploads = [_to_upload_read(upload) for upload in project.uploads]
    readiness_issues = _readiness_issues(project)
    generator_input = _generator_input_summary(project, db)

    def reveal(value: str | None) -> str | None:
        if db is None or role is None:
            return value
        return _reveal_pii_for_role(db, role, project, value)

    sections = []
    for section in project.sections:
        section_dict = _section_to_dict(section)
        for key in ("goal", "responsible", "staff"):
            if key in section_dict:
                section_dict[key] = reveal(section_dict.get(key))
        sections.append(section_dict)

    return ProjectRead(
        slug=project.slug,
        name=reveal(project.name),
        project_type=project.project_type,
        address=reveal(project.address),
        client_name=reveal(project.client_name),
        responsible=reveal(project.responsible),
        construction_manager=reveal(project.construction_manager),
        foreman=reveal(project.foreman),
        planned_start=project.planned_start,
        planned_end=project.planned_end,
        notes=reveal(project.notes),
        sections=sections,
        status=project.status,
        preview_url=_preview_url(project.slug),
        uploads=uploads,
        upload_count=len(uploads),
        generator_input=generator_input,
        ready_for_generation=len(readiness_issues) == 0,
        readiness_issues=readiness_issues,
        documentation_checklist=_documentation_checklist(project),
        planned_outputs=_planned_outputs(project),
        hero_project_match_id=project.hero_project_match_id,
    )


def _project_or_404(db: Session, slug: str) -> Project:
    from app.db.orm_models import HeatingDesign, Offer

    project = (
        db.query(Project)
        .options(
            selectinload(Project.sections)
            .selectinload(ProjectSection.staff_members)
            .selectinload(ProjectSectionStaff.user),
            selectinload(Project.uploads),
            selectinload(Project.heating_design).selectinload(HeatingDesign.circuits),
            selectinload(Project.offers).selectinload(Offer.items),
            selectinload(Project.members),
        )
        .filter(Project.slug == slug)
        .one_or_none()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _assign_section_staff(
    db: Session,
    section: ProjectSection,
    user_ids: list[int],
) -> None:
    """Replace section staff with the given user_ids.

    Invalid user_ids (non-existing or inactive users) are silently ignored.
    Duplicate ids are deduplicated.
    """
    section.staff_members.clear()
    if not user_ids:
        return

    unique_ids = list(dict.fromkeys(user_ids))
    found_users = (
        db.query(User).filter(User.id.in_(unique_ids), User.active.is_(True)).all()
    )
    for user in found_users:
        section.staff_members.append(ProjectSectionStaff(user_id=user.id))


def _to_generation_run_read(run: GenerationRun) -> GenerationRunRead:
    return GenerationRunRead(
        id=run.id,
        slug=run.project.slug,
        status=run.status,
        returncode=run.returncode,
        stdout=run.stdout,
        stderr=run.stderr,
        progress_current=run.progress_current,
        progress_total=run.progress_total,
        current_step=run.current_step,
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


@router.post("", response_model=ProjectWorkspace)
def create_project(
    project: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectWorkspace:
    require_global_role(current_user, ADMIN_ROLES)

    if not project.sections:
        raise HTTPException(status_code=400, detail="At least one section is required")

    db_sections: list[tuple[ProjectSection, list[int]]] = []
    for section in project.sections:
        db_section = ProjectSection(
            number=section.number,
            name=section.name,
            goal=section.goal,
            planned_hours=section.planned_hours,
            responsible=section.responsible,
            staff=section.staff,
        )
        db_sections.append((db_section, list(section.staff_user_ids)))

    db_project = Project(
        slug=project.slug,
        name=project.name,
        project_type=project.project_type,
        address=project.address,
        client_name=project.client_name,
        responsible=project.responsible,
        construction_manager=project.construction_manager,
        foreman=project.foreman,
        planned_start=project.planned_start,
        planned_end=project.planned_end,
        notes=project.notes,
        sections=[entry[0] for entry in db_sections],
    )
    db.add(db_project)

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Project slug already exists") from exc

    for db_section, user_ids in db_sections:
        _assign_section_staff(db, db_section, user_ids)

    try:
        workspace = create_project_workspace(project)
    except OSError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Could not create project workspace: {exc}",
        ) from exc

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Project slug already exists") from exc

    return workspace


@router.get("", response_model=list[ProjectRead])
def list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProjectRead]:
    from app.db.orm_models import HeatingDesign, Offer
    query = db.query(Project).options(
        selectinload(Project.sections),
        selectinload(Project.uploads),
        selectinload(Project.heating_design).selectinload(HeatingDesign.circuits),
        selectinload(Project.offers).selectinload(Offer.items),
        selectinload(Project.members),
    )

    if current_user.global_role not in ADMIN_ROLES:
        query = query.join(ProjectMember).filter(ProjectMember.user_id == current_user.id)

    projects = query.order_by(Project.created_at.desc()).all()
    return [
        _to_project_read(project, db, resolve_effective_role(db, current_user, project))
        for project in projects
    ]


@router.get("/{slug}", response_model=ProjectRead)
def get_project(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectRead:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    role = resolve_effective_role(db, current_user, project)
    return _to_project_read(project, db, role)


@router.put("/{slug}", response_model=ProjectRead)
def update_project(
    slug: str,
    update: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectRead:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)

    if not update.sections:
        raise HTTPException(status_code=400, detail="At least one section is required")

    project.name = update.name
    project.project_type = update.project_type
    project.address = update.address
    project.client_name = update.client_name
    project.responsible = update.responsible
    project.construction_manager = update.construction_manager
    project.foreman = update.foreman
    project.planned_start = update.planned_start
    project.planned_end = update.planned_end
    project.notes = update.notes

    project.sections.clear()
    db.flush()
    new_sections: list[tuple[ProjectSection, list[int]]] = []
    for section in update.sections:
        db_section = ProjectSection(
            number=section.number,
            name=section.name,
            goal=section.goal,
            planned_hours=section.planned_hours,
            responsible=section.responsible,
            staff=section.staff,
        )
        project.sections.append(db_section)
        new_sections.append((db_section, list(section.staff_user_ids)))

    db.flush()
    for db_section, user_ids in new_sections:
        _assign_section_staff(db, db_section, user_ids)

    db.commit()
    db.refresh(project)
    role = resolve_effective_role(db, current_user, project)
    return _to_project_read(project, db, role)


@router.get("/{slug}/outputs", response_model=ProjectOutputsRead)
def list_project_outputs(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectOutputsRead:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    effective_role = resolve_effective_role(db, current_user, project)
    allowed = allowed_output_folders(effective_role)
    excluded = ROLE_OUTPUT_EXCLUSIONS.get(effective_role) or frozenset()
    if allowed is None:
        visible_folders: list[str] = []
    else:
        visible_folders = sorted(allowed)

    output_root = _project_output_root(slug)
    return ProjectOutputsRead(
        slug=slug,
        preview_url=_preview_url(slug),
        published=output_root.exists(),
        files=_list_output_files(slug, allowed, excluded),
        versions=_list_output_versions(slug, allowed),
        visible_folders=visible_folders,
    )


# Roles that see project documents in full clear text — they need access
# to all PII (customer name, address, contact details) for site-lead work.
_CLEARTEXT_OUTPUT_ROLES = SITE_LEAD_ROLES

# Roles that get a partial reveal: only the project's staff names
# (responsible / construction manager / foreman) so the holder knows who
# to contact on site. Customer PII (address, phone, IBAN, ...) stays
# tokenised — those roles get that info from the CRM, not from the
# generated documents.
_PARTIAL_REVEAL_ROLES = frozenset({"monteur"})

# File extensions whose contents we read as UTF-8 and rewrite. Everything
# else (images, PDFs, etc.) is streamed unchanged — they don't carry
# [[PII:...]] placeholders anyway.
_REIDENTIFIABLE_SUFFIXES = {".html", ".htm", ".md", ".markdown", ".txt", ".csv", ".json"}

_TEXT_MEDIA_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".markdown": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".json": "application/json",
}


def _project_staff_names(project: Project) -> list[str]:
    """Names that internal staff (even Monteur) may see un-tokenised so
    they know who to contact on site."""
    return [
        value
        for value in (project.responsible, project.construction_manager, project.foreman)
        if value and value.strip()
    ]


def _reidentify_for_role(text: str, role: str, project: Project, db: Session) -> str:
    if role in _CLEARTEXT_OUTPUT_ROLES:
        revealed, _ = pii_tokenizer.reidentify_text(db, text)
        return revealed
    if role in _PARTIAL_REVEAL_ROLES:
        revealed, _ = pii_tokenizer.reidentify_text_partial(
            db, text, _project_staff_names(project)
        )
        return revealed
    return text


def _read_with_reidentification(
    path: Path,
    role: str,
    project: Project,
    db: Session,
) -> tuple[bytes, str | None]:
    """Return (body_bytes, media_type) for an output file.

    For roles that get any level of un-tokenisation AND text-like files,
    reads the file as UTF-8, applies the role-appropriate reidentify
    strategy (full reveal vs. project-staff-only partial reveal), and
    returns bytes + media type. Otherwise returns raw bytes so the caller
    can hand them to FileResponse unchanged.
    """
    suffix = path.suffix.lower()
    needs_rewrite = (
        suffix in _REIDENTIFIABLE_SUFFIXES
        and role in (_CLEARTEXT_OUTPUT_ROLES | _PARTIAL_REVEAL_ROLES)
    )
    if not needs_rewrite:
        return path.read_bytes(), None

    text = path.read_text(encoding="utf-8", errors="replace")
    revealed = _reidentify_for_role(text, role, project, db)
    # HTML gets the form-sync snippet so checkboxes/contenteditable cells
    # persist user input via the form-responses API. Other text formats
    # (Markdown, CSV, JSON, plaintext) stay unchanged.
    if suffix in {".html", ".htm"}:
        revealed = inject_form_sync_snippet(revealed)
    media_type = _TEXT_MEDIA_TYPES.get(suffix, "text/plain; charset=utf-8")
    return revealed.encode("utf-8"), media_type


@router.get("/{slug}/outputs/file/{relative_path:path}")
def get_project_output_file(
    slug: str,
    relative_path: str,
    current_user: User = Depends(get_current_user_query_or_header),
    db: Session = Depends(get_db),
):
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    effective_role = resolve_effective_role(db, current_user, project)
    allowed = allowed_output_folders(effective_role)
    excluded = ROLE_OUTPUT_EXCLUSIONS.get(effective_role) or frozenset()
    source_path = _safe_output_path(slug, relative_path, allowed, excluded)

    body, media_type = _read_with_reidentification(source_path, effective_role, project, db)
    if media_type is None:
        return FileResponse(source_path)
    return Response(content=body, media_type=media_type)


@router.get("/{slug}/outputs/pdf/{relative_path:path}")
def get_project_output_pdf(
    slug: str,
    relative_path: str,
    current_user: User = Depends(get_current_user_query_or_header),
    db: Session = Depends(get_db),
) -> Response:
    """Render a project output HTML file on-the-fly as a PDF.

    The PDF is not cached on disk (MVP); each request re-renders. RBAC and
    path-traversal checks reuse the existing ``_safe_output_path`` helper.
    """
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    effective_role = resolve_effective_role(db, current_user, project)
    allowed = allowed_output_folders(effective_role)
    excluded = ROLE_OUTPUT_EXCLUSIONS.get(effective_role) or frozenset()
    source_path = _safe_output_path(slug, relative_path, allowed, excluded)

    if source_path.suffix.lower() != ".html":
        raise HTTPException(
            status_code=400,
            detail="Only HTML files can be rendered to PDF",
        )

    try:
        if effective_role in (_CLEARTEXT_OUTPUT_ROLES | _PARTIAL_REVEAL_ROLES):
            html_text = source_path.read_text(encoding="utf-8", errors="replace")
            html_text = _reidentify_for_role(html_text, effective_role, project, db)
            pdf_bytes = render_html_string_to_pdf(
                html_text,
                base_url=source_path.parent,
                source_label=source_path.name,
            )
        else:
            pdf_bytes = render_html_to_pdf(source_path)
    except PdfRenderError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    pdf_filename = f"{source_path.stem}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{pdf_filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/{slug}/uploads", response_model=ProjectUploadRead)
def upload_project_file(
    slug: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectUploadRead:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)

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
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GenerateResponse:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)

    workspace_path = settings.workspaces_path / slug
    input_path = workspace_path / "input.json"

    if not input_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Project workspace not found. Create the project before starting generation.",
        )

    write_heating_design_json(slug, project.heating_design)
    write_offers_json(slug, project.offers or [])
    has_heating_design = project.heating_design is not None

    voice_notes = (
        db.query(VoiceNote)
        .options(selectinload(VoiceNote.user))
        .filter(VoiceNote.project_id == project.id)
        .order_by(VoiceNote.created_at.asc())
        .all()
    )
    write_voice_notes_to_workspace(slug, voice_notes)

    project_photos = (
        db.query(ProjectPhoto)
        .filter(ProjectPhoto.project_id == project.id)
        .order_by(ProjectPhoto.created_at.asc())
        .all()
    )
    copy_photos_to_workspace(slug, project_photos)

    # New template-based pipeline: 3 phases (extract / render / snapshot).
    # The progress bar reflects that, not the legacy per-document task count.
    total_phases = 3
    prompt = (
        f"Template-basierter Generator-Run für {project.project_type}-Projekt.\n"
        f"Phase 1: Daten-Extraktion via LLM aus briefing.md + Voicenotes + Angebot-PDFs.\n"
        f"Phase 2: Rendering aller {len(SLUG_TO_FILENAME_PREVIEW)} Dokument-Vorlagen aus document_templates.\n"
        f"Phase 3: Snapshot nach storage/projects/{slug}/_versions/.\n"
        f"Zusätzlicher Kontext-Prompt:\n{request.prompt or '(keiner)'}"
    )
    provider_pool = get_provider_pool()
    provider_names = ",".join(p.name for p in provider_pool)
    primary = provider_pool[0]
    command = (
        primary.build_command(str(workspace_path))
        if hasattr(primary, "build_command")
        else [primary.name]
    )

    if not request.run_codex:
        return GenerateResponse(
            slug=slug,
            command=command,
            returncode=None,
            stdout=(
                f"Dry run only. Set run_codex=true to execute. "
                f"Provider pool: {provider_names}."
            ),
            stderr=prompt,
            status="dry_run",
            progress_current=0,
            progress_total=total_phases,
            current_step="Dry-Run",
        )

    generation_run = GenerationRun(
        project_id=project.id,
        status="queued",
        codex_profile=f"{provider_names}:{settings.codex_profile}",
        prompt=prompt,
        progress_current=0,
        progress_total=total_phases,
        current_step="Wartet auf Start",
    )
    db.add(generation_run)
    db.commit()
    db.refresh(generation_run)
    project.status = "generation_queued"
    db.commit()
    background_tasks.add_task(_run_generation_job, generation_run.id)

    return GenerateResponse(
        slug=slug,
        command=command,
        returncode=None,
        stdout="Generatorlauf wurde gestartet.",
        stderr="",
        run_id=generation_run.id,
        status=generation_run.status,
        progress_current=generation_run.progress_current,
        progress_total=generation_run.progress_total,
        current_step=generation_run.current_step,
    )


@router.get("/{slug}/generate/{run_id}", response_model=GenerationRunRead)
def get_generation_run(
    slug: str,
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GenerationRunRead:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    run = (
        db.query(GenerationRun)
        .options(selectinload(GenerationRun.project))
        .filter(GenerationRun.id == run_id, GenerationRun.project_id == project.id)
        .one_or_none()
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Generation run not found")
    return _to_generation_run_read(run)


def _run_generation_job(run_id: int) -> None:
    """Entry point for BackgroundTasks. Runs the async pipeline in a worker thread
    so the FastAPI event loop is not blocked by long Codex/Claude calls."""

    def _runner() -> None:
        asyncio.run(_run_generation_job_async(run_id))

    thread = threading.Thread(target=_runner, name=f"generation-{run_id}", daemon=True)
    thread.start()


async def _run_generation_job_async(run_id: int) -> None:
    """Template-based generation pipeline. Three phases:

    1. **Extraktion**  — LLM (Codex/Claude) liest briefing.md + Voicenotes +
       Angebot-PDFs und liefert pro Domäne JSON, das in die ORM-Tabellen
       (Project, Sections, Personnel, Risks, Material) geschrieben wird.
       Hydraulik-Excels werden parallel über den deterministischen
       heating_importer eingelesen.
    2. **Rendering**   — alle 25 Dokument-Templates aus ``document_templates``
       werden mit den frisch extrahierten Daten gerendert und unter
       ``storage/projects/<slug>/`` abgelegt (gleicher Pfad wie früher,
       gleiche Dateinamen — frontend-kompatibel).
    3. **Snapshot**    — Kopie nach ``storage/projects/<slug>/_versions/run-<id>/``.
    """
    from app.services.data_extractor import run_full_extraction

    with SessionLocal() as db:
        from app.db.orm_models import HeatingDesign, Offer

        run = (
            db.query(GenerationRun)
            .options(
                selectinload(GenerationRun.project).selectinload(Project.sections),
                selectinload(GenerationRun.project)
                .selectinload(Project.heating_design)
                .selectinload(HeatingDesign.circuits),
                selectinload(GenerationRun.project)
                .selectinload(Project.offers)
                .selectinload(Offer.items),
            )
            .filter(GenerationRun.id == run_id)
            .one_or_none()
        )
        if run is None:
            return

        project = run.project
        slug = project.slug

        # Pre-stage source material into the workspace so the LLM has a
        # stable disk-based view of briefing/voicenotes/photos.
        write_heating_design_json(slug, project.heating_design)
        write_offers_json(slug, project.offers or [])
        voice_notes = (
            db.query(VoiceNote)
            .options(selectinload(VoiceNote.user))
            .filter(VoiceNote.project_id == project.id)
            .order_by(VoiceNote.created_at.asc())
            .all()
        )
        write_voice_notes_to_workspace(slug, voice_notes)
        project_photos = (
            db.query(ProjectPhoto)
            .filter(ProjectPhoto.project_id == project.id)
            .order_by(ProjectPhoto.created_at.asc())
            .all()
        )
        copy_photos_to_workspace(slug, project_photos)

        run.status = "filtering"
        run.current_step = "Quelldaten anonymisieren"
        run.progress_current = 0
        run.progress_total = 3  # extract, render, snapshot
        project.status = "filtering"
        db.commit()

        try:
            generator_workspace = prepare_sanitized_generator_workspace(db, slug)
        except Exception as exc:
            run.returncode = 1
            run.stderr = f"Filter-Pipeline fehlgeschlagen: {exc}"
            run.status = "failed"
            run.current_step = "Fehler im Filter"
            run.finished_at = datetime.now(timezone.utc)
            project.status = "generation_failed"
            db.commit()
            return

        # ── Phase 1: Daten-Extraktion ─────────────────────────────────────
        provider_pool = get_provider_pool()
        provider = provider_pool[0]
        run.status = "running"
        run.current_step = "Daten-Extraktion (LLM)"
        run.progress_current = 0
        project.status = "generating"
        db.commit()

        try:
            report = run_full_extraction(db, project, provider, str(generator_workspace))
            db.refresh(project)
            run.stdout = "===== extraction =====\n" + json.dumps(report, default=str, indent=2)
            run.progress_current = 1
            db.commit()
        except Exception as exc:
            run.returncode = 1
            run.stderr = f"Daten-Extraktion fehlgeschlagen: {exc}"
            run.status = "failed"
            run.current_step = f"Extraktion fehlgeschlagen: {exc}"
            run.finished_at = datetime.now(timezone.utc)
            project.status = "generation_failed"
            db.commit()
            return

        # ── Phase 2: Templates rendern ────────────────────────────────────
        run.current_step = "Templates rendern"
        db.commit()
        try:
            published = template_publisher.publish_templates_to_storage(db, slug)
            run.stdout = (run.stdout or "") + (
                f"\n\n===== templates =====\n"
                f"{len(published)} Vorlagen aus Datenbank gerendert.\n"
                + "\n".join(f"  {p.relative_path} ({p.bytes_written} B)" for p in published)
            )
            run.progress_current = 2
            db.commit()
        except Exception as exc:
            run.returncode = 1
            run.stderr = (run.stderr or "") + f"\n\n===== templates =====\n{exc}"
            run.status = "failed"
            run.current_step = f"Template-Render fehlgeschlagen: {exc}"
            run.finished_at = datetime.now(timezone.utc)
            project.status = "generation_failed"
            db.commit()
            return

        # ── Phase 3: Snapshot der gerenderten HTMLs ───────────────────────
        run.status = "publishing"
        run.current_step = "Snapshot ablegen"
        db.commit()
        try:
            _snapshot_published(slug, run.id)
            run.progress_current = 3
        except Exception as exc:
            # Snapshot ist nice-to-have; Hauptoutput in storage/projects ist da.
            run.stderr = (run.stderr or "") + f"\n\n===== snapshot (Warnung) =====\n{exc}"

        run.returncode = 0
        run.status = "completed"
        run.current_step = "Fertig"
        project.status = "published"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()


def _snapshot_published(slug: str, run_id: int) -> None:
    """Copy the just-rendered storage/projects/<slug>/ into _versions/run-<id>/."""
    public = settings.projects_path / slug
    versions = public / "_versions" / f"run-{run_id}"
    if versions.exists():
        shutil.rmtree(versions)
    versions.mkdir(parents=True, exist_ok=True)
    for item in public.iterdir():
        if item.name == "_versions":
            continue
        target = versions / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


@router.post("/{slug}/publish", response_model=PublishResponse)
def publish_existing_project(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PublishResponse:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)

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
