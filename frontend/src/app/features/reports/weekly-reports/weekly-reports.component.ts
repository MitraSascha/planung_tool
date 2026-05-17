import { CommonModule } from '@angular/common';
import { Component, Input, OnChanges, SimpleChanges, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { WeeklyReportRead } from '../../../core/models';
import { NotificationService } from '../../../core/services/notification.service';
import { ReportsService } from '../../../core/services/reports.service';
import { formatHttpError } from '../../../core/services/error-format';
import { EmptyStateComponent } from '../../../shared/components/empty-state/empty-state.component';
import {
  formatDate,
  formatDateTime,
  reportStatusLabel,
} from '../../../shared/utils/format';

@Component({
  selector: 'app-weekly-reports',
  imports: [CommonModule, RouterLink, EmptyStateComponent],
  templateUrl: './weekly-reports.component.html',
  styleUrl: './weekly-reports.component.scss',
})
export class WeeklyReportsComponent implements OnChanges {
  private readonly reports = inject(ReportsService);
  private readonly notifications = inject(NotificationService);
  private readonly router = inject(Router);

  @Input() slug!: string;

  protected readonly loading = signal(false);
  protected readonly expandedId = signal<number | null>(null);

  protected readonly allReports = computed<WeeklyReportRead[]>(
    () => this.reports.weeklyReports()[this.slug] ?? [],
  );

  protected readonly formatDate = formatDate;
  protected readonly formatDateTime = formatDateTime;
  protected readonly reportStatusLabel = reportStatusLabel;

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['slug'] && this.slug) {
      this.loadAll();
    }
  }

  protected toggleExpanded(id: number): void {
    this.expandedId.set(this.expandedId() === id ? null : id);
  }

  protected createReport(): void {
    this.router.navigate(['/projects', this.slug, 'reports', 'weekly', 'new']);
  }

  private loadAll(): void {
    this.loading.set(true);
    this.reports.loadWeeklyReports(this.slug).subscribe({
      next: () => this.loading.set(false),
      error: (response) => {
        this.loading.set(false);
        this.notifications.showError(
          formatHttpError(response, 'Wochenberichte konnten nicht geladen werden.'),
        );
      },
    });
  }
}
