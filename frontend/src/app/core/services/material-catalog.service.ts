import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export interface MaterialCatalogEntry {
  id: number;
  artikelnummer: string;
  beschreibung_1: string;
  beschreibung_2: string | null;
  listenpreis_eur: number | null;
  nettowert_eur: number | null;
  einheit: string | null;
  kategorie: string | null;
}

/**
 * Materialkatalog: kuratierte Listen aus ``Material*.csv`` im Repo-Root,
 * vom Chef gepflegt. Wird im Tagesbericht-Form als Dropdown angeboten.
 * Pro CSV eine Kategorie (standard / brandschutz / isolierung).
 */
@Injectable({ providedIn: 'root' })
export class MaterialCatalogService {
  private readonly http = inject(HttpClient);

  list(
    q?: string,
    kategorie?: string | null,
    limit = 200,
  ): Observable<MaterialCatalogEntry[]> {
    let params = new HttpParams().set('limit', String(limit));
    const trimmed = (q ?? '').trim();
    if (trimmed) params = params.set('q', trimmed);
    const kat = (kategorie ?? '').trim();
    if (kat) params = params.set('kategorie', kat);
    return this.http.get<MaterialCatalogEntry[]>('/api/material-catalog', { params });
  }

  listCategories(): Observable<string[]> {
    return this.http.get<string[]>('/api/material-catalog/categories');
  }
}
