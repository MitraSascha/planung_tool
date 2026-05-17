export type ReportStatus = 'green' | 'yellow' | 'red' | string;

export type IssueStatus = 'open' | 'in_progress' | 'done' | string;
export type MaterialPriority = 'low' | 'normal' | 'high' | 'urgent' | string;
export type BlockerSeverity = 'low' | 'medium' | 'high' | 'critical' | string;

export interface DailyReportRead {
  id: number;
  project_slug: string;
  user_id: number;
  username: string;
  display_name: string;
  section_number?: number | null;
  report_date: string;
  status: ReportStatus;
  team?: string | null;
  completed_work?: string | null;
  open_work?: string | null;
  material_missing?: string | null;
  blockers?: string | null;
  notes?: string | null;
  ist_hours?: number | null;
  safety_psa?: boolean | null;
  safety_tools?: boolean | null;
  safety_material?: boolean | null;
  safety_workarea?: boolean | null;
  safety_approval?: boolean | null;
  created_at: string;
}

export interface DailyReportForm {
  section_number: number | null;
  report_date: string;
  status: ReportStatus;
  team: string;
  completed_work: string;
  open_work: string;
  material_missing: string;
  blockers: string;
  notes: string;
  ist_hours?: number | null;
  safety_psa?: boolean | null;
  safety_tools?: boolean | null;
  safety_material?: boolean | null;
  safety_workarea?: boolean | null;
  safety_approval?: boolean | null;
}

export interface WeeklyReportRead {
  id: number;
  project_slug: string;
  user_id: number;
  username: string;
  display_name: string;
  week_start: string;
  week_end: string;
  status: ReportStatus;
  summary?: string | null;
  next_week_plan?: string | null;
  manpower_notes?: string | null;
  material_notes?: string | null;
  risks?: string | null;
  created_at: string;
}

export interface WeeklyReportForm {
  week_start: string;
  week_end: string;
  status: ReportStatus;
  summary: string;
  next_week_plan: string;
  manpower_notes: string;
  material_notes: string;
  risks: string;
}

export interface MaterialIssueCreate {
  section_number: number | null;
  description: string;
  priority: MaterialPriority;
}

export interface BlockerCreate {
  section_number: number | null;
  description: string;
  severity: BlockerSeverity;
}

export interface ReportSummary {
  project_slug: string;
  daily_reports: number;
  weekly_reports: number;
  material_issues_open: number;
  blockers_open: number;
  status_green: number;
  status_yellow: number;
  status_red: number;
}
