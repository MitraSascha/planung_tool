import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  ExternalSourceMapping,
  ExternalSourceMappingWrite,
  HeatingDesignImportPreview,
  HeatingDesignRead,
  HeatingDesignWrite,
  HeatingImporterInfo,
} from '../models';

@Injectable({ providedIn: 'root' })
export class HeatingService {
  private readonly http = inject(HttpClient);

  get(slug: string): Observable<HeatingDesignRead | null> {
    return this.http.get<HeatingDesignRead | null>(
      `/api/projects/${slug}/heating-design`,
    );
  }

  upsert(slug: string, payload: HeatingDesignWrite): Observable<HeatingDesignRead> {
    return this.http.put<HeatingDesignRead>(
      `/api/projects/${slug}/heating-design`,
      payload,
    );
  }

  remove(slug: string): Observable<void> {
    return this.http.delete<void>(`/api/projects/${slug}/heating-design`);
  }

  // -------------------------------------------------------------
  // Import workflow
  // -------------------------------------------------------------

  listImporters(): Observable<HeatingImporterInfo[]> {
    return this.http.get<HeatingImporterInfo[]>('/api/heating-importers');
  }

  importPreview(
    slug: string,
    file: File,
    adapterHint?: string | null,
    mappingName?: string | null,
    mappingJson?: string | null,
  ): Observable<HeatingDesignImportPreview> {
    const data = new FormData();
    data.append('file', file, file.name);
    if (adapterHint) {
      data.append('adapter_hint', adapterHint);
    }
    if (mappingName) {
      data.append('mapping_name', mappingName);
    }
    if (mappingJson) {
      data.append('mapping_json', mappingJson);
    }
    return this.http.post<HeatingDesignImportPreview>(
      `/api/projects/${slug}/heating-design/import`,
      data,
    );
  }

  importConfirm(
    slug: string,
    preview: HeatingDesignImportPreview,
  ): Observable<HeatingDesignRead> {
    return this.http.post<HeatingDesignRead>(
      `/api/projects/${slug}/heating-design/import/confirm`,
      preview,
    );
  }

  // -------------------------------------------------------------
  // External-source mapping persistence (generic_table)
  // -------------------------------------------------------------

  listMappings(importerSource?: string): Observable<ExternalSourceMapping[]> {
    let params = new HttpParams();
    if (importerSource) {
      params = params.set('importer_source', importerSource);
    }
    return this.http.get<ExternalSourceMapping[]>(
      '/api/external-source-mappings',
      { params },
    );
  }

  saveMapping(
    name: string,
    body: ExternalSourceMappingWrite,
  ): Observable<ExternalSourceMapping> {
    return this.http.put<ExternalSourceMapping>(
      `/api/external-source-mappings/${encodeURIComponent(name)}`,
      body,
    );
  }

  deleteMapping(name: string): Observable<void> {
    return this.http.delete<void>(
      `/api/external-source-mappings/${encodeURIComponent(name)}`,
    );
  }
}
