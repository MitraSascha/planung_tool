import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export interface HeroStatus {
  configured: boolean;
  graphql_url: string | null;
}

export interface HeroPartner {
  id: number;
  full_name: string;
  email: string | null;
}

export interface HeroPartnerSyncResult {
  matched: number;
  ambiguous: number;
  unchanged: number;
  no_match: number;
}

/** Eintrag aus der globalen HERO-ProjectMatch-Suche. */
export interface HeroProjectHit {
  id: number;
  name: string;
  project_nr?: string | null;
  measure?: { name?: string | null; short?: string | null } | null;
  current_project_match_status?: { name?: string | null } | null;
  customer?: { full_name?: string | null } | null;
}

@Injectable({ providedIn: 'root' })
export class HeroService {
  private readonly http = inject(HttpClient);

  status(): Observable<HeroStatus> {
    return this.http.get<HeroStatus>('/api/hero/status');
  }

  syncPartners(): Observable<HeroPartnerSyncResult> {
    return this.http.post<HeroPartnerSyncResult>('/api/hero/sync-partners', {});
  }

  listPartners(): Observable<HeroPartner[]> {
    return this.http.get<HeroPartner[]>('/api/hero/partners');
  }

  searchProjects(q: string, first = 10): Observable<HeroProjectHit[]> {
    const params = new HttpParams().set('q', q).set('first', String(first));
    return this.http.get<HeroProjectHit[]>('/api/hero/search-projects', { params });
  }

  setProjectMapping(
    slug: string,
    heroProjectMatchId: number | null,
  ): Observable<{ slug: string; hero_project_match_id: number | null }> {
    return this.http.patch<{ slug: string; hero_project_match_id: number | null }>(
      `/api/hero/projects/${slug}/mapping`,
      { hero_project_match_id: heroProjectMatchId },
    );
  }

  dryRunDailyReport(reportId: number): Observable<any[]> {
    return this.http.get<any[]>(`/api/hero/dry-run/daily-reports/${reportId}`);
  }
}
