import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  OfferImporterInfo,
  OfferImportPreview,
  OfferPdfUploadForm,
  OfferRead,
  OfferSummary,
} from '../models';

@Injectable({ providedIn: 'root' })
export class OfferService {
  private readonly http = inject(HttpClient);

  listImporters(): Observable<OfferImporterInfo[]> {
    return this.http.get<OfferImporterInfo[]>('/api/offer-importers');
  }

  list(slug: string): Observable<OfferSummary[]> {
    return this.http.get<OfferSummary[]>(`/api/projects/${slug}/offers`);
  }

  get(slug: string, offerId: number): Observable<OfferRead> {
    return this.http.get<OfferRead>(`/api/projects/${slug}/offers/${offerId}`);
  }

  remove(slug: string, offerId: number): Observable<void> {
    return this.http.delete<void>(`/api/projects/${slug}/offers/${offerId}`);
  }

  importPreview(
    slug: string,
    file: File,
    adapterHint?: string | null,
  ): Observable<OfferImportPreview> {
    const data = new FormData();
    data.append('file', file, file.name);
    if (adapterHint) {
      data.append('adapter_hint', adapterHint);
    }
    return this.http.post<OfferImportPreview>(
      `/api/projects/${slug}/offers/import`,
      data,
    );
  }

  importConfirm(slug: string, preview: OfferImportPreview): Observable<OfferRead> {
    return this.http.post<OfferRead>(
      `/api/projects/${slug}/offers/import/confirm`,
      preview,
    );
  }

  uploadPdf(slug: string, file: File, form: OfferPdfUploadForm): Observable<OfferRead> {
    const data = new FormData();
    data.append('file', file, file.name);
    data.append('supplier_name', form.supplier_name);
    if (form.offer_no) data.append('offer_no', form.offer_no);
    if (form.offer_date) data.append('offer_date', form.offer_date);
    if (form.total_net_eur != null) data.append('total_net_eur', String(form.total_net_eur));
    if (form.total_gross_eur != null) data.append('total_gross_eur', String(form.total_gross_eur));
    if (form.vat_rate != null) data.append('vat_rate', String(form.vat_rate));
    if (form.notes) data.append('notes', form.notes);
    return this.http.post<OfferRead>(`/api/projects/${slug}/offers/pdf`, data);
  }

  attachmentUrl(slug: string, offerId: number): string {
    return `/api/projects/${slug}/offers/${offerId}/attachment`;
  }
}
