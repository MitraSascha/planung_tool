import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { PhotoUploadOptions, ProjectPhotoRead, ProjectPhotoUpdate } from '../models/photo.model';

@Injectable({ providedIn: 'root' })
export class PhotoService {
  private readonly http = inject(HttpClient);

  /** List photos for a project, optionally filtered by section or daily-report id. */
  list(
    slug: string,
    sectionNumber?: number | null,
    dailyReportId?: number | null,
  ): Observable<ProjectPhotoRead[]> {
    let params = new HttpParams();
    if (sectionNumber !== undefined && sectionNumber !== null) {
      params = params.set('section_number', String(sectionNumber));
    }
    if (dailyReportId !== undefined && dailyReportId !== null) {
      params = params.set('daily_report_id', String(dailyReportId));
    }
    return this.http.get<ProjectPhotoRead[]>(`/api/projects/${slug}/photos`, { params });
  }

  /** Upload a photo (multipart) with optional metadata. */
  upload(
    slug: string,
    file: File | Blob,
    opts: PhotoUploadOptions = {},
  ): Observable<ProjectPhotoRead> {
    const formData = new FormData();
    const filename = file instanceof File ? file.name : 'photo.jpg';
    formData.append('file', file, filename);
    if (opts.sectionNumber !== undefined && opts.sectionNumber !== null) {
      formData.append('section_number', String(opts.sectionNumber));
    }
    if (opts.dailyReportId !== undefined && opts.dailyReportId !== null) {
      formData.append('daily_report_id', String(opts.dailyReportId));
    }
    if (opts.caption !== undefined && opts.caption !== null && opts.caption.length > 0) {
      formData.append('caption', opts.caption);
    }
    return this.http.post<ProjectPhotoRead>(`/api/projects/${slug}/photos`, formData);
  }

  /** Upload an annotation PNG layer/composite for an existing photo. */
  uploadAnnotation(
    slug: string,
    photoId: number,
    pngBlob: Blob,
  ): Observable<ProjectPhotoRead> {
    const formData = new FormData();
    formData.append('file', pngBlob, 'annotation.png');
    return this.http.post<ProjectPhotoRead>(
      `/api/projects/${slug}/photos/${photoId}/annotation`,
      formData,
    );
  }

  /** Partially update photo metadata. */
  update(
    slug: string,
    photoId: number,
    patch: ProjectPhotoUpdate,
  ): Observable<ProjectPhotoRead> {
    return this.http.patch<ProjectPhotoRead>(
      `/api/projects/${slug}/photos/${photoId}`,
      patch,
    );
  }

  /** Delete a photo (and its annotated overlay if present). */
  delete(slug: string, photoId: number): Observable<void> {
    return this.http.delete<void>(`/api/projects/${slug}/photos/${photoId}`);
  }

  /** Convenience helper: URL for the original photo. */
  viewUrl(slug: string, photoId: number): string {
    return `/api/projects/${slug}/photos/${photoId}/raw`;
  }

  /** Convenience helper: URL for the annotated overlay (PNG). */
  annotatedUrl(slug: string, photoId: number): string {
    return `/api/projects/${slug}/photos/${photoId}/annotated`;
  }
}
