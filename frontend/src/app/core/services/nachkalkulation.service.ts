import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export interface NachkalkulationItem {
  item_id: number;
  artikelnummer: string | null;
  name: string;
  unit: string | null;
  ist_qty: number;
  preis_eur: number | null;
  position_sum: number;
  note: string | null;
}

export interface NachkalkulationSection {
  section_number: number | null;
  section_name: string | null;
  items: NachkalkulationItem[];
  subtotal: number;
  item_count: number;
}

export interface NachkalkulationResult {
  project_slug: string;
  project_name: string;
  items_total: number;
  sections_total: number;
  grand_total: number;
  items_verbaut: number;
  sections: NachkalkulationSection[];
}

@Injectable({ providedIn: 'root' })
export class NachkalkulationService {
  private readonly http = inject(HttpClient);

  get(slug: string): Observable<NachkalkulationResult> {
    return this.http.get<NachkalkulationResult>(
      `/api/projects/${slug}/nachkalkulation`,
    );
  }

  /** Liefert die CSV als Blob — der Caller erzeugt daraus eine Download-URL. */
  csv(slug: string): Observable<Blob> {
    return this.http.get(`/api/projects/${slug}/nachkalkulation.csv`, {
      responseType: 'blob',
    });
  }
}
