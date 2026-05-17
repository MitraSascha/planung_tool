export type HeatingSource =
  | 'manual'
  | 'viptool_xlsx'
  | 'viptool_ifc'
  | 'generic_table'
  | 'ifc'
  | string;

export interface HeatingCircuitRead {
  id: number;
  position: number;
  strand: string | null;
  room: string | null;
  floor: string | null;
  radiator_type: string | null;
  area_sqm: number | null;
  heat_load_w: number | null;
  volume_flow_lph: number | null;
  pressure_drop_pa: number | null;
  pipe_length_m: number | null;
  valve_type: string | null;
  valve_preset: string | null;
  kv_value: number | null;
  notes: string | null;
}

export interface HeatingDesignRead {
  id: number;
  project_slug: string;
  system_type: string | null;
  supply_temp_c: number | null;
  return_temp_c: number | null;
  delta_t_k: number | null;
  pump_head_pa: number | null;
  total_volume_flow_lph: number | null;
  pump_model: string | null;
  notes: string | null;
  source: HeatingSource;
  source_file: string | null;
  imported_at: string;
  imported_by_user_id: number | null;
  imported_by_username: string | null;
  updated_at: string;
  circuits: HeatingCircuitRead[];
}

export interface HeatingCircuitWrite {
  position: number;
  strand: string | null;
  room: string | null;
  floor: string | null;
  radiator_type: string | null;
  heat_load_w: number | null;
  volume_flow_lph: number | null;
  pressure_drop_pa: number | null;
  pipe_length_m: number | null;
  valve_type: string | null;
  valve_preset: string | null;
  kv_value: number | null;
  notes: string | null;
}

export interface HeatingDesignWrite {
  system_type: string | null;
  supply_temp_c: number | null;
  return_temp_c: number | null;
  delta_t_k: number | null;
  pump_head_pa: number | null;
  total_volume_flow_lph: number | null;
  pump_model: string | null;
  notes: string | null;
  source: HeatingSource;
  source_file: string | null;
  circuits: HeatingCircuitWrite[];
}

// ----------------------------------------------------------------------
// Import preview / mapping types (Phase 11.3)
// ----------------------------------------------------------------------

export interface HeatingDesignBaseFields {
  system_type: string | null;
  supply_temp_c: number | null;
  return_temp_c: number | null;
  delta_t_k: number | null;
  pump_head_pa: number | null;
  total_volume_flow_lph: number | null;
  pump_model: string | null;
  notes: string | null;
}

export interface HeatingCircuitPreview {
  position: number;
  strand: string | null;
  room: string | null;
  floor: string | null;
  radiator_type: string | null;
  area_sqm: number | null;
  heat_load_w: number | null;
  volume_flow_lph: number | null;
  pressure_drop_pa: number | null;
  pipe_length_m: number | null;
  valve_type: string | null;
  valve_preset: string | null;
  kv_value: number | null;
  notes: string | null;
}

export interface HeatingDesignImportPreview {
  source: HeatingSource;
  source_file: string;
  design: HeatingDesignBaseFields;
  circuits: HeatingCircuitPreview[];
  warnings: string[];
  detected_columns: Record<string, string>;
  /** Header name → up to 5 sample values from data rows (for manual mapping dropdowns). */
  source_columns: Record<string, string[]>;
}

export interface HeatingImporterInfo {
  source_name: string;
  display_name: string;
  accepts_extensions: string;
}

export interface ExternalSourceMappingColumnMap {
  circuit_columns?: Record<string, string>;
  design_overrides?: Record<string, string | number | null>;
}

export interface ExternalSourceMapping {
  id: number;
  name: string;
  description: string | null;
  importer_source: string;
  column_map: ExternalSourceMappingColumnMap;
  created_at: string;
}

export interface ExternalSourceMappingWrite {
  description?: string | null;
  importer_source?: string;
  column_map: ExternalSourceMappingColumnMap;
}

// Canonical circuit field names (must match backend KNOWN_CIRCUIT_FIELDS).
export const KNOWN_CIRCUIT_FIELDS: ReadonlyArray<keyof HeatingCircuitPreview> = [
  'strand',
  'room',
  'floor',
  'area_sqm',
  'radiator_type',
  'heat_load_w',
  'volume_flow_lph',
  'pressure_drop_pa',
  'pipe_length_m',
  'valve_type',
  'valve_preset',
  'kv_value',
  'notes',
];

export const CIRCUIT_FIELD_LABELS: Record<string, string> = {
  strand: 'Strang',
  room: 'Wohnung / Raum',
  floor: 'Etage',
  area_sqm: 'Fläche (m²)',
  radiator_type: 'Heizkörper-Typ',
  heat_load_w: 'Heizlast (W)',
  volume_flow_lph: 'Volumenstrom (l/h)',
  pressure_drop_pa: 'Druckverlust (Pa)',
  pipe_length_m: 'Rohrlänge (m)',
  valve_type: 'Ventiltyp',
  valve_preset: 'Voreinstellung',
  kv_value: 'kv-Wert',
  notes: 'Notizen',
};

/**
 * Felder, die typisch nur in echten Hydraulik-Strang-Berechnungen
 * (VIPtool, ETU) vorkommen — bei VDI-Heizlast-Aggregaten fehlen sie immer.
 * Werden im UI in 'Weitere Felder' eingeklappt statt prominent angezeigt.
 */
export const SECONDARY_CIRCUIT_FIELDS = new Set<keyof HeatingCircuitPreview>([
  'pressure_drop_pa',
  'pipe_length_m',
  'valve_type',
  'valve_preset',
  'kv_value',
  'radiator_type',
  'notes',
]);
