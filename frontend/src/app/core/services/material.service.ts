import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  ArticleHit,
  MaterialAnalytics,
  MaterialItem,
  MaterialUsageCreate,
  MaterialUsageRead,
} from '../models';

interface ArtikelstammAvailability { available: boolean }

interface CreateFromArtikelstammResponse {
  id: number;
  duplicate: boolean;
  name?: string;
  unit?: string | null;
  artikelnummer?: string;
  preis_eur?: number | null;
  source?: string;
  message?: string;
}

@Injectable({ providedIn: 'root' })
export class MaterialService {
  private readonly http = inject(HttpClient);

  listItems(slug: string): Observable<MaterialItem[]> {
    return this.http.get<MaterialItem[]>(`/api/projects/${slug}/material-items`);
  }

  /** Live-Suche im externen Artikelstamm (DATANORM, > 2 Mio Artikel). */
  searchArtikelstamm(q: string, limit = 30): Observable<ArticleHit[]> {
    const params = new HttpParams().set('q', q).set('limit', String(limit));
    return this.http.get<ArticleHit[]>('/api/articles/search', { params });
  }

  isArtikelstammAvailable(): Observable<ArtikelstammAvailability> {
    return this.http.get<ArtikelstammAvailability>('/api/articles/availability');
  }

  /** Legt aus einem Artikelstamm-Eintrag einen MaterialItem im Projekt an
   *  und markiert ihn als source='artikelstamm'. Idempotent: doppelter
   *  Aufruf für denselben Artikel im selben Projekt liefert die existierende
   *  ID zurück. */
  createMaterialFromArtikelstamm(
    slug: string,
    payload: { artikelnummer: string; soll_qty?: number | null; section_number?: number | null; note?: string | null },
  ): Observable<CreateFromArtikelstammResponse> {
    return this.http.post<CreateFromArtikelstammResponse>(
      `/api/projects/${slug}/material-items/from-artikelstamm`,
      payload,
    );
  }

  listUsages(
    slug: string,
    filters: {
      materialItemId?: number;
      dailyReportId?: number;
      von?: string;
      bis?: string;
    } = {},
  ): Observable<MaterialUsageRead[]> {
    let params = new HttpParams();
    if (filters.materialItemId !== undefined) {
      params = params.set('material_item_id', String(filters.materialItemId));
    }
    if (filters.dailyReportId !== undefined) {
      params = params.set('daily_report_id', String(filters.dailyReportId));
    }
    if (filters.von) {
      params = params.set('von', filters.von);
    }
    if (filters.bis) {
      params = params.set('bis', filters.bis);
    }
    return this.http.get<MaterialUsageRead[]>(
      `/api/projects/${slug}/material-usages`,
      { params },
    );
  }

  createUsage(slug: string, payload: MaterialUsageCreate): Observable<MaterialUsageRead> {
    return this.http.post<MaterialUsageRead>(
      `/api/projects/${slug}/material-usages`,
      payload,
    );
  }

  deleteUsage(slug: string, usageId: number): Observable<void> {
    return this.http.delete<void>(
      `/api/projects/${slug}/material-usages/${usageId}`,
    );
  }

  getAnalytics(slug: string, weeksBack = 8): Observable<MaterialAnalytics> {
    const params = new HttpParams().set('weeks_back', String(weeksBack));
    return this.http.get<MaterialAnalytics>(
      `/api/analytics/projects/${slug}/material-analytics`,
      { params },
    );
  }
}
