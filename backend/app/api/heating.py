import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session, selectinload

from app.db.database import get_db
from app.db.orm_models import (
    ExternalSourceMapping,
    HeatingCircuit,
    HeatingDesign,
    Project,
    User,
)
from app.models.heating import (
    HeatingCircuitRead,
    HeatingDesignImportPreview,
    HeatingDesignRead,
    HeatingDesignWrite,
)
from app.services.auth import (
    PROJECT_READ_ROLES,
    SITE_LEAD_ROLES,
    get_current_user,
    require_project_role,
)
from app.services.heating_importers import (
    ColumnMapping,
    HeatingImporterError,
    available_importers,
    detect_importer,
    get_importer,
)

router = APIRouter()


@router.get("/heating-importers")
def list_heating_importers(
    current_user: User = Depends(get_current_user),
) -> list[dict[str, str]]:
    """List available importer adapters for the frontend file-picker."""
    return available_importers()


def _project_or_404(db: Session, slug: str) -> Project:
    project = (
        db.query(Project)
        .options(
            selectinload(Project.heating_design).selectinload(HeatingDesign.circuits),
            selectinload(Project.heating_design).selectinload(HeatingDesign.imported_by),
        )
        .filter(Project.slug == slug)
        .one_or_none()
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _design_to_read(project: Project, design: HeatingDesign) -> HeatingDesignRead:
    return HeatingDesignRead(
        id=design.id,
        project_slug=project.slug,
        system_type=design.system_type,
        supply_temp_c=design.supply_temp_c,
        return_temp_c=design.return_temp_c,
        delta_t_k=design.delta_t_k,
        pump_head_pa=design.pump_head_pa,
        total_volume_flow_lph=design.total_volume_flow_lph,
        pump_model=design.pump_model,
        notes=design.notes,
        source=design.source,
        source_file=design.source_file,
        imported_at=design.imported_at,
        imported_by_user_id=design.imported_by_user_id,
        imported_by_username=design.imported_by.username if design.imported_by else None,
        updated_at=design.updated_at,
        circuits=[
            HeatingCircuitRead(
                id=circuit.id,
                position=circuit.position,
                strand=circuit.strand,
                room=circuit.room,
                floor=circuit.floor,
                radiator_type=circuit.radiator_type,
                area_sqm=circuit.area_sqm,
                heat_load_w=circuit.heat_load_w,
                volume_flow_lph=circuit.volume_flow_lph,
                pressure_drop_pa=circuit.pressure_drop_pa,
                pipe_length_m=circuit.pipe_length_m,
                valve_type=circuit.valve_type,
                valve_preset=circuit.valve_preset,
                kv_value=circuit.kv_value,
                notes=circuit.notes,
            )
            for circuit in design.circuits
        ],
    )


@router.get("/projects/{slug}/heating-design", response_model=HeatingDesignRead | None)
def get_heating_design(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HeatingDesignRead | None:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    if project.heating_design is None:
        return None
    return _design_to_read(project, project.heating_design)


@router.put("/projects/{slug}/heating-design", response_model=HeatingDesignRead)
def upsert_heating_design(
    slug: str,
    payload: HeatingDesignWrite,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HeatingDesignRead:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)

    design = project.heating_design
    if design is None:
        design = HeatingDesign(project_id=project.id)
        db.add(design)
        project.heating_design = design

    design.system_type = payload.system_type
    design.supply_temp_c = payload.supply_temp_c
    design.return_temp_c = payload.return_temp_c
    design.delta_t_k = payload.delta_t_k
    design.pump_head_pa = payload.pump_head_pa
    design.total_volume_flow_lph = payload.total_volume_flow_lph
    design.pump_model = payload.pump_model
    design.notes = payload.notes
    design.source = payload.source
    design.source_file = payload.source_file
    design.imported_by_user_id = current_user.id

    design.circuits.clear()
    db.flush()
    for index, circuit in enumerate(payload.circuits):
        design.circuits.append(
            HeatingCircuit(
                position=circuit.position or index,
                strand=circuit.strand,
                room=circuit.room,
                floor=circuit.floor,
                radiator_type=circuit.radiator_type,
                area_sqm=circuit.area_sqm,
                heat_load_w=circuit.heat_load_w,
                volume_flow_lph=circuit.volume_flow_lph,
                pressure_drop_pa=circuit.pressure_drop_pa,
                pipe_length_m=circuit.pipe_length_m,
                valve_type=circuit.valve_type,
                valve_preset=circuit.valve_preset,
                kv_value=circuit.kv_value,
                notes=circuit.notes,
            )
        )

    db.commit()
    db.refresh(project)
    return _design_to_read(project, project.heating_design)


@router.delete("/projects/{slug}/heating-design", status_code=204)
def delete_heating_design(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    if project.heating_design is None:
        return
    db.delete(project.heating_design)
    db.commit()


@router.post(
    "/projects/{slug}/heating-design/import",
    response_model=HeatingDesignImportPreview,
)
async def import_heating_design_preview(
    slug: str,
    file: UploadFile = File(...),
    adapter_hint: str | None = Form(None),
    mapping_name: str | None = Form(None),
    mapping_json: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HeatingDesignImportPreview:
    """Parse an uploaded file into a HeatingDesign preview.

    The caller can pin a specific adapter (``adapter_hint``) or pass a saved
    column mapping (``mapping_name`` -> looked up from external_source_mappings,
    or ``mapping_json`` for an ad-hoc override). The result is NOT persisted;
    the caller must POST the (possibly edited) preview to /confirm.
    """
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty upload")

    if adapter_hint:
        importer = get_importer(adapter_hint)
    else:
        importer = detect_importer(file.filename or "", raw[:4096])
        if importer is None:
            raise HTTPException(
                status_code=400,
                detail="No importer accepted this file. Provide adapter_hint to override.",
            )

    column_mapping: ColumnMapping | None = None
    if mapping_json:
        try:
            parsed = json.loads(mapping_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid mapping_json: {exc}") from exc
        column_mapping = ColumnMapping(
            circuit_columns=parsed.get("circuit_columns", {}),
            design_overrides=parsed.get("design_overrides", {}),
        )
    elif mapping_name:
        stored = (
            db.query(ExternalSourceMapping)
            .filter(ExternalSourceMapping.name == mapping_name)
            .one_or_none()
        )
        if stored is None:
            raise HTTPException(status_code=404, detail="Mapping not found")
        payload = json.loads(stored.column_map_json)
        column_mapping = ColumnMapping(
            circuit_columns=payload.get("circuit_columns", {}),
            design_overrides=payload.get("design_overrides", {}),
        )

    try:
        return importer.parse(file.filename or "", raw, column_mapping)
    except HeatingImporterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/projects/{slug}/heating-design/import/confirm",
    response_model=HeatingDesignRead,
)
def import_heating_design_confirm(
    slug: str,
    preview: HeatingDesignImportPreview,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HeatingDesignRead:
    """Persist a (possibly user-edited) preview into the project's heating_design."""
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)

    design = project.heating_design
    if design is None:
        design = HeatingDesign(project_id=project.id)
        db.add(design)
        project.heating_design = design

    design.system_type = preview.design.system_type
    design.supply_temp_c = preview.design.supply_temp_c
    design.return_temp_c = preview.design.return_temp_c
    design.delta_t_k = preview.design.delta_t_k
    design.pump_head_pa = preview.design.pump_head_pa
    design.total_volume_flow_lph = preview.design.total_volume_flow_lph
    design.pump_model = preview.design.pump_model
    design.notes = preview.design.notes
    design.source = preview.source
    design.source_file = preview.source_file
    design.imported_by_user_id = current_user.id

    design.circuits.clear()
    db.flush()
    for index, circuit in enumerate(preview.circuits):
        design.circuits.append(
            HeatingCircuit(
                position=circuit.position or index,
                strand=circuit.strand,
                room=circuit.room,
                floor=circuit.floor,
                radiator_type=circuit.radiator_type,
                area_sqm=circuit.area_sqm,
                heat_load_w=circuit.heat_load_w,
                volume_flow_lph=circuit.volume_flow_lph,
                pressure_drop_pa=circuit.pressure_drop_pa,
                pipe_length_m=circuit.pipe_length_m,
                valve_type=circuit.valve_type,
                valve_preset=circuit.valve_preset,
                kv_value=circuit.kv_value,
                notes=circuit.notes,
            )
        )

    db.commit()
    db.refresh(project)
    return _design_to_read(project, project.heating_design)


# --------------------------------------------------------------------
# Mapping persistence for the generic-table importer
# --------------------------------------------------------------------


@router.get("/external-source-mappings")
def list_mappings(
    importer_source: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = db.query(ExternalSourceMapping)
    if importer_source:
        query = query.filter(ExternalSourceMapping.importer_source == importer_source)
    mappings = query.order_by(ExternalSourceMapping.name).all()
    return [
        {
            "id": m.id,
            "name": m.name,
            "description": m.description,
            "importer_source": m.importer_source,
            "column_map": json.loads(m.column_map_json),
            "created_at": m.created_at.isoformat(),
        }
        for m in mappings
    ]


@router.put("/external-source-mappings/{name}")
def upsert_mapping(
    name: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    mapping = (
        db.query(ExternalSourceMapping)
        .filter(ExternalSourceMapping.name == name)
        .one_or_none()
    )
    importer_source = payload.get("importer_source") or "generic_table"
    description = payload.get("description")
    column_map = payload.get("column_map", {})
    if not isinstance(column_map, dict):
        raise HTTPException(status_code=400, detail="column_map must be an object")

    if mapping is None:
        mapping = ExternalSourceMapping(
            name=name,
            description=description,
            importer_source=importer_source,
            column_map_json=json.dumps(column_map),
            created_by_user_id=current_user.id,
        )
        db.add(mapping)
    else:
        mapping.description = description
        mapping.importer_source = importer_source
        mapping.column_map_json = json.dumps(column_map)

    db.commit()
    db.refresh(mapping)
    return {
        "id": mapping.id,
        "name": mapping.name,
        "description": mapping.description,
        "importer_source": mapping.importer_source,
        "column_map": json.loads(mapping.column_map_json),
        "created_at": mapping.created_at.isoformat(),
    }


@router.delete("/external-source-mappings/{name}", status_code=204)
def delete_mapping(
    name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    mapping = (
        db.query(ExternalSourceMapping)
        .filter(ExternalSourceMapping.name == name)
        .one_or_none()
    )
    if mapping is None:
        return
    db.delete(mapping)
    db.commit()
