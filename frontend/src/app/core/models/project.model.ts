export type ProjectType = 'standard' | 'small';

export type ProjectStatus =
  | 'draft'
  | 'generated'
  | 'generation_queued'
  | 'filtering'
  | 'generating'
  | 'generation_failed'
  | 'generation_failed_partial'
  | 'publish_failed'
  | 'published'
  | string;

export interface ProjectSection {
  number: number;
  name: string;
  goal?: string;
  planned_hours?: number | null;
  responsible?: string;
  staff?: string;
}

export interface ProjectForm {
  slug: string;
  name: string;
  project_type: ProjectType;
  address?: string;
  client_name?: string;
  responsible?: string;
  construction_manager?: string;
  foreman?: string;
  planned_start?: string;
  planned_end?: string;
  notes?: string;
  sections: ProjectSection[];
}

export interface ProjectUploadRead {
  filename: string;
  path: string;
  content_type?: string | null;
  size_bytes?: number | null;
  created_at?: string | null;
}

export interface GeneratorOfferSummary {
  id: number;
  supplier_name: string;
  offer_no?: string | null;
  offer_date?: string | null;
  source_file?: string | null;
  position_count: number;
  total_net_eur?: number | null;
  created_at?: string | null;
}

export interface HeatingDesignSummary {
  source?: string | null;
  source_file?: string | null;
  circuit_count: number;
  system_type?: string | null;
  pump_model?: string | null;
  imported_at?: string | null;
}

export interface GeneratorInputSummary {
  upload_count: number;
  offer_count: number;
  offer_position_count: number;
  offers: GeneratorOfferSummary[];
  heating?: HeatingDesignSummary | null;
  material_item_count: number;
  material_item_with_offer_link: number;
  section_count: number;
  member_count: number;
}

export interface ProjectRead extends ProjectForm {
  status: ProjectStatus;
  preview_url?: string | null;
  uploads: ProjectUploadRead[];
  upload_count: number;
  generator_input?: GeneratorInputSummary;
  ready_for_generation: boolean;
  readiness_issues: string[];
  documentation_checklist: string[];
  planned_outputs: string[];
}

export interface ProjectOutputFile {
  path: string;
  filename: string;
  extension: string;
  size_bytes: number;
  view_url: string;
}

export interface ProjectOutputVersion {
  label: string;
  file_count: number;
  created_at?: string | null;
}

export interface ProjectOutputsRead {
  slug: string;
  preview_url?: string | null;
  published: boolean;
  files: ProjectOutputFile[];
  versions: ProjectOutputVersion[];
  visible_folders?: string[];
}
