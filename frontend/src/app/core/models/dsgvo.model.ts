export type RetentionAction = 'delete' | 'anonymize';

export interface RetentionRuleRead {
  id: number;
  entity_type: string;
  ttl_days: number;
  action: RetentionAction | string;
  enabled: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface RetentionRuleUpsert {
  entity_type: string;
  ttl_days: number;
  action: RetentionAction;
  enabled: boolean;
  description?: string | null;
}

export interface AnonymizeResponse {
  slug: string;
  updated_rows: number;
  errors: string[];
}

export interface DeleteProjectResponse {
  slug: string;
  deleted_project_id: number;
  removed_files: number;
  removed_dirs: number;
}

export interface CleanupRuleStats {
  action: string;
  ttl_days?: number;
  cutoff?: string;
  affected: number;
  executed?: number;
  skipped?: boolean;
  reason?: string;
}

export interface CleanupResponse {
  dry_run: boolean;
  rules: Record<string, CleanupRuleStats>;
}
