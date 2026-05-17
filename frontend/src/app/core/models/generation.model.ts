export interface GenerateStartResponse {
  run_id?: number | null;
  status?: string | null;
  progress_current: number;
  progress_total: number;
  current_step?: string | null;
  stdout: string;
  stderr: string;
}

export interface GenerationRunRead {
  id: number;
  slug: string;
  status: string;
  returncode?: number | null;
  stdout?: string | null;
  stderr?: string | null;
  progress_current: number;
  progress_total: number;
  current_step?: string | null;
  created_at: string;
  finished_at?: string | null;
}

export const TERMINAL_RUN_STATUSES: ReadonlyArray<string> = [
  'completed',
  'succeeded',
  'failed',
  'failed_partial',
  'publish_failed',
];
