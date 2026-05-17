import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  AnonymizeResponse,
  AuditEventFilter,
  AuditEventRead,
  CleanupResponse,
  DeleteProjectResponse,
  RetentionRuleRead,
  RetentionRuleUpsert,
} from '../models';

@Injectable({ providedIn: 'root' })
export class DsgvoService {
  private readonly http = inject(HttpClient);

  listAuditEvents(filter: AuditEventFilter = {}): Observable<AuditEventRead[]> {
    let params = new HttpParams();
    if (filter.entity_type) params = params.set('entity_type', filter.entity_type);
    if (filter.project_slug) params = params.set('project_slug', filter.project_slug);
    if (filter.action) params = params.set('action', filter.action);
    if (filter.from) params = params.set('from', filter.from);
    if (filter.to) params = params.set('to', filter.to);
    params = params.set('limit', String(filter.limit ?? 200));
    return this.http.get<AuditEventRead[]>('/api/audit/events', { params });
  }

  listRetentionRules(): Observable<RetentionRuleRead[]> {
    return this.http.get<RetentionRuleRead[]>('/api/dsgvo/retention-rules');
  }

  upsertRetentionRule(rule: RetentionRuleUpsert): Observable<RetentionRuleRead> {
    return this.http.put<RetentionRuleRead>('/api/dsgvo/retention-rules', rule);
  }

  deleteRetentionRule(entityType: string): Observable<{ deleted: string }> {
    return this.http.delete<{ deleted: string }>(
      `/api/dsgvo/retention-rules/${encodeURIComponent(entityType)}`,
    );
  }

  runCleanup(dryRun: boolean): Observable<CleanupResponse> {
    const params = new HttpParams().set('dry_run', dryRun ? 'true' : 'false');
    return this.http.post<CleanupResponse>('/api/dsgvo/retention-rules/cleanup', null, {
      params,
    });
  }

  anonymizeProject(slug: string): Observable<AnonymizeResponse> {
    return this.http.post<AnonymizeResponse>(
      `/api/dsgvo/projects/${encodeURIComponent(slug)}/anonymize`,
      {},
    );
  }

  deleteProject(slug: string, confirm: string): Observable<DeleteProjectResponse> {
    return this.http.post<DeleteProjectResponse>(
      `/api/dsgvo/projects/${encodeURIComponent(slug)}/delete`,
      { confirm },
    );
  }
}
