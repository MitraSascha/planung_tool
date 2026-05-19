export interface StatusBreakdown {
  green: number;
  yellow: number;
  red: number;
  total: number;
}

export interface TimeSeriesPoint {
  date: string;
  value: number;
  label?: string | null;
}

export interface TopItem {
  label: string;
  count: number;
  severity?: string | null;
}

export interface HoursPerUser {
  user_id: number;
  display_name: string;
  soll_hours: number;
  ist_hours: number;
  days: number;
}

export type HoursStatus = 'under' | 'on_track' | 'over' | 'unknown';

export interface HoursPerSection {
  section_number: number | null;
  section_name: string | null;
  ist_hours: number;
  user_count: number;
  report_count: number;
  planned_hours?: number | null;
  delta_hours?: number | null;
  percent_done?: number | null;
  status: HoursStatus;
}

export interface ProjectAnalytics {
  project_slug: string;
  project_name: string;
  period_start: string;
  period_end: string;
  daily_status: StatusBreakdown;
  weekly_status: StatusBreakdown;
  blockers_open: number;
  blockers_total: number;
  blockers_by_severity: Record<string, number>;
  material_open: number;
  material_total: number;
  risks_open: number;
  risks_total: number;
  materials_by_status: Record<string, number>;
  hours_total_soll: number;
  hours_total_ist: number;
  hours_total_planned: number;
  hours_total_delta: number;
  hours_total_percent: number | null;
  hours_total_status: HoursStatus;
  hours_by_user: HoursPerUser[];
  hours_by_section: HoursPerSection[];
  daily_status_series: TimeSeriesPoint[];
  blockers_opened_per_day: TimeSeriesPoint[];
  offer_total_net?: number | null;
  offer_count: number;
  top_blockers: TopItem[];
  top_material_issues: TopItem[];
}

export interface AtRiskProject {
  slug: string;
  name: string;
  recent_red_reports: number;
  critical_blockers: number;
}

export interface PortfolioAnalytics {
  generated_at: string;
  project_count: number;
  active_project_count: number;
  projects_at_risk: AtRiskProject[];
  total_hours_ist_last_7d: number;
  total_hours_soll_last_7d: number;
  open_blockers_total: number;
  open_material_total: number;
  open_risks_total: number;
  total_offer_value_net: number;
}
