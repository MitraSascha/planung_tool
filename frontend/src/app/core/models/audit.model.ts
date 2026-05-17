export type AuditAction =
  | 'create'
  | 'update'
  | 'delete'
  | 'anonymize'
  | 'login'
  | 'export';

export interface AuditEventRead {
  id: number;
  user_id: number | null;
  action: AuditAction | string;
  entity_type: string;
  entity_id: string | null;
  project_slug: string | null;
  changes_json: string | null;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
}

export interface AuditEventFilter {
  entity_type?: string;
  project_slug?: string;
  action?: string;
  from?: string;
  to?: string;
  limit?: number;
}
