export type AnomalyKind = 'consecutive_red' | 'recurring_material' | 'stale_blocker' | string;
export type AnomalySeverity = 'info' | 'warning' | 'critical' | string;

export interface AnomalyRead {
  project_slug: string;
  kind: AnomalyKind;
  severity: AnomalySeverity;
  title: string;
  detail: string;
  related_ids: number[];
  detected_at: string;
}

export interface WeeklyReportDraftRequest {
  week_start: string;
  week_end: string;
}

export interface WeeklyReportDraftRead {
  summary: string;
  next_week_plan: string;
  manpower_notes: string;
  material_notes: string;
  risks: string;
  status: 'green' | 'yellow' | 'red' | string;
}
