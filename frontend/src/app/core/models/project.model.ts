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

export interface ProjectRead extends ProjectForm {
  status: ProjectStatus;
  preview_url?: string | null;
  uploads: ProjectUploadRead[];
  upload_count: number;
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
