from datetime import datetime

from pydantic import BaseModel, Field


HeatingSource = str  # "manual" | "viptool_xlsx" | "viptool_ifc" | "generic_table" | "ifc"


class HeatingCircuitBase(BaseModel):
    position: int = 0
    strand: str | None = None
    room: str | None = None
    floor: str | None = None
    radiator_type: str | None = None
    area_sqm: float | None = None
    heat_load_w: float | None = None
    volume_flow_lph: float | None = None
    pressure_drop_pa: float | None = None
    pipe_length_m: float | None = None
    valve_type: str | None = None
    valve_preset: str | None = None
    kv_value: float | None = None
    notes: str | None = None


class HeatingCircuitRead(HeatingCircuitBase):
    id: int


class HeatingDesignBase(BaseModel):
    system_type: str | None = None
    supply_temp_c: float | None = None
    return_temp_c: float | None = None
    delta_t_k: float | None = None
    pump_head_pa: float | None = None
    total_volume_flow_lph: float | None = None
    pump_model: str | None = None
    notes: str | None = None


class HeatingDesignWrite(HeatingDesignBase):
    source: HeatingSource = "manual"
    source_file: str | None = None
    circuits: list[HeatingCircuitBase] = Field(default_factory=list)


class HeatingDesignRead(HeatingDesignBase):
    id: int
    project_slug: str
    source: HeatingSource
    source_file: str | None = None
    imported_at: datetime
    imported_by_user_id: int | None = None
    imported_by_username: str | None = None
    updated_at: datetime
    circuits: list[HeatingCircuitRead] = Field(default_factory=list)


class HeatingDesignImportPreview(BaseModel):
    """Preview returned by an importer before the user confirms persistence."""

    source: HeatingSource
    source_file: str
    design: HeatingDesignBase
    circuits: list[HeatingCircuitBase]
    warnings: list[str] = Field(default_factory=list)
    detected_columns: dict[str, str] = Field(default_factory=dict)
    # Header name -> up to 5 sample values from the first data rows.
    # Lets the UI show "Header (Sample1, Sample2, ...)" in the mapping
    # dropdown so users can actually see what each column contains.
    source_columns: dict[str, list[str]] = Field(default_factory=dict)
