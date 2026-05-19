export type ReportStatus = 'green' | 'yellow' | 'red' | string;

export type IssueStatus = 'open' | 'in_progress' | 'done' | string;
export type MaterialPriority = 'low' | 'normal' | 'high' | 'urgent' | string;
export type BlockerSeverity = 'low' | 'medium' | 'high' | 'critical' | string;
/** Beschaffungs-Workflow (Stepper) für Materialmeldungen. */
export type ProcurementStatus = 'offen' | 'bestellt' | 'unterwegs' | 'angekommen';

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
  attendee_user_ids?: number[];
  completed_work?: string | null;
  open_work?: string | null;
  /** Roh-Eingabe der „Arbeitstagerfassung". Backend splittet via LLM in
   *  completed_work + open_work; dieser Text bleibt persistent als Quelle. */
  raw_work_log?: string | null;
  /** ISO 639-1 Sprach-Code der Voice-Aufnahme (falls vorhanden). */
  raw_work_log_language?: string | null;
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
  /** true: aktueller User darf diesen Bericht noch bearbeiten (Owner im
   *  Edit-Fenster oder Lead-Rolle). Vom Backend pro Request berechnet. */
  editable?: boolean;
}

export interface DailyReportForm {
  section_number: number | null;
  report_date: string;
  status: ReportStatus;
  team: string;
  attendee_user_ids: number[];
  /** Roh-Eingabe der „Arbeitstagerfassung" (was wurde gemacht + was bleibt
   *  offen — in einem Feld, KI strukturiert beim Speichern). */
  raw_work_log: string;
  /** ISO 639-1 — wird vom Push-to-Talk-Button gesetzt, wenn die Voice-Quelle
   *  nicht-deutsch war. Bei reiner Texteingabe leer/undefined. */
  raw_work_log_language?: string | null;
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

export interface MaterialIssueRead {
  id: number;
  project_slug: string;
  user_id: number;
  username: string;
  display_name: string;
  section_number?: number | null;
  description: string;
  priority: MaterialPriority;
  status: IssueStatus;
  created_at: string;
  /** Beschaffungs-Workflow-Stufe (Stepper). */
  procurement_status: ProcurementStatus;
  ordered_at?: string | null;
  ordered_by_username?: string | null;
  shipped_at?: string | null;
  shipped_by_username?: string | null;
  arrived_at?: string | null;
  arrived_by_username?: string | null;
}

export interface ProcurementStatusUpdate {
  procurement_status: ProcurementStatus;
}

export interface BlockerCreate {
  section_number: number | null;
  description: string;
  severity: BlockerSeverity;
}

export interface BlockerRead {
  id: number;
  project_slug: string;
  user_id: number;
  username: string;
  display_name: string;
  section_number?: number | null;
  description: string;
  severity: BlockerSeverity;
  status: IssueStatus;
  created_at: string;
}

export interface IssueStatusUpdate {
  status: 'open' | 'in_progress' | 'done';
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
