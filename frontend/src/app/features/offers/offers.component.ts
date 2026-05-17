import { CommonModule } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import {
  OfferImportPreview,
  OfferRead,
  OfferSummary,
} from '../../core/models';
import { NotificationService } from '../../core/services/notification.service';
import { OfferService } from '../../core/services/offer.service';
import { formatHttpError } from '../../core/services/error-format';

type Mode = 'list' | 'detail' | 'import-preview' | 'pdf-form';

@Component({
  selector: 'app-offers',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './offers.component.html',
  styleUrl: './offers.component.scss',
})
export class OffersComponent implements OnInit {
  protected readonly offerService = inject(OfferService);
  private readonly notifications = inject(NotificationService);
  private readonly route = inject(ActivatedRoute);

  protected readonly slug = signal<string>('');
  protected readonly offers = signal<OfferSummary[]>([]);
  protected readonly mode = signal<Mode>('list');
  protected readonly busy = signal(false);

  // Detail view
  protected readonly detail = signal<OfferRead | null>(null);

  // Import-preview state (xlsx/csv/ugl)
  protected readonly preview = signal<OfferImportPreview | null>(null);
  protected selectedFile: File | null = null;
  protected selectedFileName = '';

  // PDF upload form
  protected pdfForm = {
    file: null as File | null,
    fileName: '',
    supplier_name: '',
    offer_no: '',
    offer_date: '',
    total_net_eur: null as number | null,
    total_gross_eur: null as number | null,
    vat_rate: 19,
    notes: '',
  };

  protected readonly totalSum = computed(() =>
    this.offers().reduce((sum, o) => sum + (o.total_net_eur ?? 0), 0),
  );

  ngOnInit(): void {
    const slug = this.route.snapshot.paramMap.get('slug');
    if (!slug) {
      this.notifications.showError('Projekt-Slug fehlt im Pfad.');
      return;
    }
    this.slug.set(slug);
    this.reload();
  }

  protected reload(): void {
    if (!this.slug()) return;
    this.busy.set(true);
    this.offerService.list(this.slug()).subscribe({
      next: (list) => {
        this.offers.set(list);
        this.busy.set(false);
      },
      error: (err) => {
        this.busy.set(false);
        this.notifications.showError(formatHttpError(err, 'Angebote konnten nicht geladen werden.'));
      },
    });
  }

  // ---------------------------------------------------------------
  // Detail
  // ---------------------------------------------------------------

  protected openDetail(summary: OfferSummary): void {
    this.busy.set(true);
    this.offerService.get(this.slug(), summary.id).subscribe({
      next: (offer) => {
        this.detail.set(offer);
        this.mode.set('detail');
        this.busy.set(false);
      },
      error: (err) => {
        this.busy.set(false);
        this.notifications.showError(formatHttpError(err, 'Angebot konnte nicht geladen werden.'));
      },
    });
  }

  protected closeDetail(): void {
    this.detail.set(null);
    this.mode.set('list');
  }

  protected deleteOffer(offer: OfferSummary, event: MouseEvent): void {
    event.stopPropagation();
    if (!confirm(`Angebot "${offer.supplier_name}" (${offer.offer_no ?? 'ohne Nr.'}) wirklich löschen?`)) {
      return;
    }
    this.busy.set(true);
    this.offerService.remove(this.slug(), offer.id).subscribe({
      next: () => {
        this.notifications.showMessage('Angebot gelöscht.');
        this.busy.set(false);
        this.reload();
      },
      error: (err) => {
        this.busy.set(false);
        this.notifications.showError(formatHttpError(err, 'Löschen fehlgeschlagen.'));
      },
    });
  }

  // ---------------------------------------------------------------
  // Import flow (xlsx / csv / ugl)
  // ---------------------------------------------------------------

  protected onTableFileChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files && input.files.length > 0 ? input.files[0] : null;
    this.selectedFile = file;
    this.selectedFileName = file ? file.name : '';
    if (file) {
      this.startImportPreview(file);
    }
  }

  private startImportPreview(file: File): void {
    this.busy.set(true);
    this.offerService.importPreview(this.slug(), file).subscribe({
      next: (preview) => {
        this.preview.set(preview);
        this.mode.set('import-preview');
        this.busy.set(false);
      },
      error: (err) => {
        this.busy.set(false);
        this.notifications.showError(formatHttpError(err, 'Datei konnte nicht eingelesen werden.'));
      },
    });
  }

  protected confirmImport(): void {
    const preview = this.preview();
    if (!preview) return;
    if (!preview.offer.supplier_name?.trim()) {
      this.notifications.showError('Lieferantenname ist erforderlich.');
      return;
    }
    this.busy.set(true);
    this.offerService.importConfirm(this.slug(), preview).subscribe({
      next: () => {
        this.notifications.showMessage('Angebot importiert.');
        this.busy.set(false);
        this.preview.set(null);
        this.selectedFile = null;
        this.selectedFileName = '';
        this.mode.set('list');
        this.reload();
      },
      error: (err) => {
        this.busy.set(false);
        this.notifications.showError(formatHttpError(err, 'Import fehlgeschlagen.'));
      },
    });
  }

  protected cancelPreview(): void {
    this.preview.set(null);
    this.selectedFile = null;
    this.selectedFileName = '';
    this.mode.set('list');
  }

  // ---------------------------------------------------------------
  // PDF flow
  // ---------------------------------------------------------------

  protected openPdfForm(): void {
    this.pdfForm = {
      file: null,
      fileName: '',
      supplier_name: '',
      offer_no: '',
      offer_date: '',
      total_net_eur: null,
      total_gross_eur: null,
      vat_rate: 19,
      notes: '',
    };
    this.mode.set('pdf-form');
  }

  protected onPdfFileChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files && input.files.length > 0 ? input.files[0] : null;
    this.pdfForm.file = file;
    this.pdfForm.fileName = file ? file.name : '';
  }

  protected submitPdf(): void {
    if (!this.pdfForm.file) {
      this.notifications.showError('Bitte PDF-Datei auswählen.');
      return;
    }
    if (!this.pdfForm.supplier_name.trim()) {
      this.notifications.showError('Lieferantenname ist erforderlich.');
      return;
    }
    this.busy.set(true);
    this.offerService
      .uploadPdf(this.slug(), this.pdfForm.file, {
        supplier_name: this.pdfForm.supplier_name.trim(),
        offer_no: this.pdfForm.offer_no.trim() || undefined,
        offer_date: this.pdfForm.offer_date || undefined,
        total_net_eur: this.pdfForm.total_net_eur ?? undefined,
        total_gross_eur: this.pdfForm.total_gross_eur ?? undefined,
        vat_rate: this.pdfForm.vat_rate ?? undefined,
        notes: this.pdfForm.notes.trim() || undefined,
      })
      .subscribe({
        next: () => {
          this.notifications.showMessage('PDF-Angebot angelegt.');
          this.busy.set(false);
          this.mode.set('list');
          this.reload();
        },
        error: (err) => {
          this.busy.set(false);
          this.notifications.showError(formatHttpError(err, 'Upload fehlgeschlagen.'));
        },
      });
  }

  protected cancelPdf(): void {
    this.mode.set('list');
  }

  // ---------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------

  protected formatEur(value: number | null | undefined): string {
    if (value == null) return '–';
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
    }).format(value);
  }

  protected sourceTypeLabel(type: string): string {
    switch (type) {
      case 'xlsx': return 'Excel';
      case 'csv': return 'CSV';
      case 'ugl': return 'UGL';
      case 'pdf': return 'PDF';
      case 'manual': return 'Manuell';
      default: return type;
    }
  }

  protected attachmentUrl(summary: OfferSummary): string {
    return this.offerService.attachmentUrl(this.slug(), summary.id);
  }
}
