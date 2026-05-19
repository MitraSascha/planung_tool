import { CommonModule } from '@angular/common';
import { Component, Input, OnChanges, OnInit, SimpleChanges, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { DailyReportRead, ProjectPhotoRead, ProjectRead } from '../../../core/models';
import { NotificationService } from '../../../core/services/notification.service';
import { PhotoService } from '../../../core/services/photo.service';
import { ProjectService } from '../../../core/services/project.service';
import { ReportsService } from '../../../core/services/reports.service';
import { formatHttpError } from '../../../core/services/error-format';
import { EmptyStateComponent } from '../../../shared/components/empty-state/empty-state.component';
import {
  formatDate,
  formatDateTime,
  reportStatusLabel,
} from '../../../shared/utils/format';

interface LightboxState {
  url: string;
  caption: string | null;
  filename: string;
}

@Component({
  selector: 'app-daily-reports',
  imports: [CommonModule, FormsModule, RouterLink, EmptyStateComponent],
  templateUrl: './daily-reports.component.html',
  styleUrl: './daily-reports.component.scss',
})
export class DailyReportsComponent implements OnChanges, OnInit {
  private readonly reports = inject(ReportsService);
  private readonly projects = inject(ProjectService);
  private readonly photos = inject(PhotoService);
  private readonly notifications = inject(NotificationService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  @Input() slug!: string;

  protected readonly project = signal<ProjectRead | null>(null);
  protected readonly loading = signal(false);
  protected readonly expandedId = signal<number | null>(null);

  protected readonly filterStatus = signal<string>('all');
  protected readonly filterSection = signal<string>('all');
  protected readonly filterFrom = signal<string>('');
  protected readonly filterTo = signal<string>('');

  /** Per-report photo cache keyed by daily-report id. */
  protected readonly photosByReport = signal<Record<number, ProjectPhotoRead[]>>({});
  protected readonly lightbox = signal<LightboxState | null>(null);

  protected readonly allReports = computed<DailyReportRead[]>(
    () => this.reports.dailyReports()[this.slug] ?? [],
  );

  protected readonly filteredReports = computed<DailyReportRead[]>(() => {
    const status = this.filterStatus();
    const section = this.filterSection();
    const from = this.filterFrom();
    const to = this.filterTo();
    return this.allReports().filter((report) => {
      if (status !== 'all' && report.status !== status) {
        return false;
      }
      if (section !== 'all' && String(report.section_number ?? '') !== section) {
        return false;
      }
      if (from && report.report_date < from) {
        return false;
      }
      if (to && report.report_date > to) {
        return false;
      }
      return true;
    });
  });

  protected readonly formatDate = formatDate;
  protected readonly formatDateTime = formatDateTime;
  protected readonly reportStatusLabel = reportStatusLabel;

  ngOnInit(): void {
    // QueryParam-Deep-Link: ?status=red|yellow|green&section=2&from=…&to=…
    // erlaubt dem Projektüberblick, direkt auf die gefilterte Liste zu
    // verlinken (Karte „Status rot" → diese Komponente vorgefiltert).
    this.route.queryParamMap.subscribe((params) => {
      const status = params.get('status');
      if (status) this.filterStatus.set(status);
      const section = params.get('section');
      if (section) this.filterSection.set(section);
      const from = params.get('from');
      if (from) this.filterFrom.set(from);
      const to = params.get('to');
      if (to) this.filterTo.set(to);
    });

    // Stelle sicher dass die Liste auch beim ersten Mount geladen wird,
    // wenn ngOnChanges für 'slug' nicht feuert (Routing-Edge-Case).
    if (this.slug) {
      this.loadAll();
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['slug'] && !changes['slug'].firstChange && this.slug) {
      this.loadAll();
    }
  }

  protected toggleExpanded(id: number): void {
    const next = this.expandedId() === id ? null : id;
    this.expandedId.set(next);
    if (next !== null && this.photosByReport()[next] === undefined) {
      this.loadPhotosForReport(next);
    }
  }

  protected resetFilters(): void {
    this.filterStatus.set('all');
    this.filterSection.set('all');
    this.filterFrom.set('');
    this.filterTo.set('');
  }

  protected createReport(): void {
    this.router.navigate(['/projects', this.slug, 'reports', 'daily', 'new']);
  }

  protected photosFor(reportId: number): ProjectPhotoRead[] {
    return this.photosByReport()[reportId] ?? [];
  }

  protected openLightbox(photo: ProjectPhotoRead): void {
    const url = photo.annotated_url ?? photo.view_url;
    this.lightbox.set({
      url,
      caption: photo.caption,
      filename: photo.filename,
    });
  }

  protected closeLightbox(): void {
    this.lightbox.set(null);
  }

  protected hasExif(photo: ProjectPhotoRead): boolean {
    return !!photo.taken_at || (photo.geo_lat !== null && photo.geo_lng !== null);
  }

  protected formatGeo(photo: ProjectPhotoRead): string | null {
    if (photo.geo_lat === null || photo.geo_lng === null) {
      return null;
    }
    return `${photo.geo_lat.toFixed(5)}, ${photo.geo_lng.toFixed(5)}`;
  }

  private loadPhotosForReport(reportId: number): void {
    this.photos.list(this.slug, undefined, reportId).subscribe({
      next: (photos) => {
        this.photosByReport.update((current) => ({ ...current, [reportId]: photos }));
      },
      error: () => {
        this.photosByReport.update((current) => ({ ...current, [reportId]: [] }));
      },
    });
  }

  private loadAll(): void {
    this.loading.set(true);
    this.photosByReport.set({});
    this.projects.get(this.slug).subscribe({
      next: (project) => this.project.set(project),
      error: () => undefined,
    });
    this.reports.loadDailyReports(this.slug).subscribe({
      next: () => this.loading.set(false),
      error: (response) => {
        this.loading.set(false);
        this.notifications.showError(
          formatHttpError(response, 'Tagesberichte konnten nicht geladen werden.'),
        );
      },
    });
  }
}
