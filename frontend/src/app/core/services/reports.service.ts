import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, tap } from 'rxjs';

import {
  AnomalyRead,
  BlockerCreate,
  BlockerRead,
  DailyReportForm,
  DailyReportRead,
  IssueStatusUpdate,
  MaterialIssueCreate,
  MaterialIssueRead,
  ProcurementStatusUpdate,
  ProjectMemberRead,
  ProjectRole,
  ReportSummary,
  WeeklyReportDraftRead,
  WeeklyReportDraftRequest,
  WeeklyReportForm,
  WeeklyReportRead,
} from '../models';

export interface AddMemberPayload {
  user_id: number;
  project_role: ProjectRole | string;
}

@Injectable({ providedIn: 'root' })
export class ReportsService {
  private readonly http = inject(HttpClient);

  private readonly membersSignal = signal<Record<string, ProjectMemberRead[]>>({});
  private readonly dailyReportsSignal = signal<Record<string, DailyReportRead[]>>({});
  private readonly weeklyReportsSignal = signal<Record<string, WeeklyReportRead[]>>({});
  private readonly summariesSignal = signal<Record<string, ReportSummary>>({});
  private readonly materialIssuesSignal = signal<Record<string, MaterialIssueRead[]>>({});
  private readonly blockersSignal = signal<Record<string, BlockerRead[]>>({});

  readonly members = this.membersSignal.asReadonly();
  readonly dailyReports = this.dailyReportsSignal.asReadonly();
  readonly weeklyReports = this.weeklyReportsSignal.asReadonly();
  readonly summaries = this.summariesSignal.asReadonly();
  readonly materialIssues = this.materialIssuesSignal.asReadonly();
  readonly blockers = this.blockersSignal.asReadonly();

  loadMembers(slug: string): Observable<ProjectMemberRead[]> {
    return this.http
      .get<ProjectMemberRead[]>(`/api/reports/projects/${slug}/members`)
      .pipe(
        tap((members) =>
          this.membersSignal.update((current) => ({ ...current, [slug]: members })),
        ),
      );
  }

  addMember(slug: string, payload: AddMemberPayload): Observable<unknown> {
    return this.http.post(`/api/reports/projects/${slug}/members`, payload);
  }

  loadDailyReports(slug: string): Observable<DailyReportRead[]> {
    return this.http
      .get<DailyReportRead[]>(`/api/reports/projects/${slug}/daily-reports`)
      .pipe(
        tap((reports) =>
          this.dailyReportsSignal.update((current) => ({ ...current, [slug]: reports })),
        ),
      );
  }

  submitDailyReport(slug: string, payload: DailyReportForm): Observable<DailyReportRead> {
    return this.http.post<DailyReportRead>(
      `/api/reports/projects/${slug}/daily-reports`,
      payload,
    );
  }

  updateDailyReport(
    slug: string,
    reportId: number,
    payload: Partial<DailyReportForm>,
  ): Observable<DailyReportRead> {
    return this.http.patch<DailyReportRead>(
      `/api/reports/projects/${slug}/daily-reports/${reportId}`,
      payload,
    );
  }

  loadWeeklyReports(slug: string): Observable<WeeklyReportRead[]> {
    return this.http
      .get<WeeklyReportRead[]>(`/api/reports/projects/${slug}/weekly-reports`)
      .pipe(
        tap((reports) =>
          this.weeklyReportsSignal.update((current) => ({ ...current, [slug]: reports })),
        ),
      );
  }

  submitWeeklyReport(slug: string, payload: WeeklyReportForm): Observable<WeeklyReportRead> {
    return this.http.post<WeeklyReportRead>(
      `/api/reports/projects/${slug}/weekly-reports`,
      payload,
    );
  }

  draftWeeklyReport(
    slug: string,
    payload: WeeklyReportDraftRequest,
  ): Observable<WeeklyReportDraftRead> {
    return this.http.post<WeeklyReportDraftRead>(
      `/api/reports/projects/${slug}/weekly-reports/draft`,
      payload,
    );
  }

  listAnomalies(slug?: string): Observable<AnomalyRead[]> {
    const url = slug
      ? `/api/reports/projects/${slug}/anomalies`
      : `/api/reports/anomalies`;
    return this.http.get<AnomalyRead[]>(url);
  }

  createMaterialIssue(slug: string, payload: MaterialIssueCreate): Observable<{ id: number }> {
    return this.http.post<{ id: number }>(
      `/api/reports/projects/${slug}/material-issues`,
      payload,
    );
  }

  loadMaterialIssues(slug: string): Observable<MaterialIssueRead[]> {
    return this.http
      .get<MaterialIssueRead[]>(`/api/reports/projects/${slug}/material-issues`)
      .pipe(
        tap((rows) =>
          this.materialIssuesSignal.update((current) => ({ ...current, [slug]: rows })),
        ),
      );
  }

  /** Bündel-Liste über alle für den User sichtbaren Projekte (Issue #1). */
  loadAllMaterialIssues(): Observable<MaterialIssueRead[]> {
    return this.http.get<MaterialIssueRead[]>('/api/reports/material-issues/all');
  }

  updateMaterialIssueStatus(
    slug: string,
    issueId: number,
    payload: IssueStatusUpdate,
  ): Observable<MaterialIssueRead> {
    return this.http
      .patch<MaterialIssueRead>(
        `/api/reports/projects/${slug}/material-issues/${issueId}`,
        payload,
      )
      .pipe(
        tap((updated) =>
          this.materialIssuesSignal.update((current) => {
            const rows = (current[slug] ?? []).map((r) => (r.id === updated.id ? updated : r));
            return { ...current, [slug]: rows };
          }),
        ),
      );
  }

  /** Beschaffungs-Stepper: setzt die Stufe (Offen/Bestellt/Unterwegs/Angekommen).
   * Backend stempelt Timestamp + User pro Stufe (Audit-Trail). */
  updateMaterialIssueProcurement(
    slug: string,
    issueId: number,
    payload: ProcurementStatusUpdate,
  ): Observable<MaterialIssueRead> {
    return this.http
      .patch<MaterialIssueRead>(
        `/api/reports/projects/${slug}/material-issues/${issueId}/procurement`,
        payload,
      )
      .pipe(
        tap((updated) =>
          this.materialIssuesSignal.update((current) => {
            const rows = (current[slug] ?? []).map((r) => (r.id === updated.id ? updated : r));
            return { ...current, [slug]: rows };
          }),
        ),
      );
  }

  createBlocker(slug: string, payload: BlockerCreate): Observable<{ id: number }> {
    return this.http.post<{ id: number }>(
      `/api/reports/projects/${slug}/blockers`,
      payload,
    );
  }

  loadBlockers(slug: string): Observable<BlockerRead[]> {
    return this.http
      .get<BlockerRead[]>(`/api/reports/projects/${slug}/blockers`)
      .pipe(
        tap((rows) =>
          this.blockersSignal.update((current) => ({ ...current, [slug]: rows })),
        ),
      );
  }

  updateBlockerStatus(
    slug: string,
    blockerId: number,
    payload: IssueStatusUpdate,
  ): Observable<BlockerRead> {
    return this.http
      .patch<BlockerRead>(
        `/api/reports/projects/${slug}/blockers/${blockerId}`,
        payload,
      )
      .pipe(
        tap((updated) =>
          this.blockersSignal.update((current) => {
            const rows = (current[slug] ?? []).map((r) => (r.id === updated.id ? updated : r));
            return { ...current, [slug]: rows };
          }),
        ),
      );
  }

  loadSummary(slug: string): Observable<ReportSummary> {
    return this.http
      .get<ReportSummary>(`/api/reports/projects/${slug}/summary`)
      .pipe(
        tap((summary) =>
          this.summariesSignal.update((current) => ({ ...current, [slug]: summary })),
        ),
      );
  }

  clear(): void {
    this.membersSignal.set({});
    this.dailyReportsSignal.set({});
    this.weeklyReportsSignal.set({});
    this.summariesSignal.set({});
    this.materialIssuesSignal.set({});
    this.blockersSignal.set({});
  }
}
