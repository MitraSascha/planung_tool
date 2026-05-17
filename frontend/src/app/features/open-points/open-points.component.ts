import { CommonModule } from '@angular/common';
import { Component, Input, OnChanges, SimpleChanges, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ReportSummary } from '../../core/models';
import { ReportsService } from '../../core/services/reports.service';
import { NotificationService } from '../../core/services/notification.service';
import { formatHttpError } from '../../core/services/error-format';

@Component({
  selector: 'app-open-points',
  imports: [CommonModule, RouterLink],
  templateUrl: './open-points.component.html',
  styleUrl: './open-points.component.scss',
})
export class OpenPointsComponent implements OnChanges {
  private readonly reports = inject(ReportsService);
  private readonly notifications = inject(NotificationService);

  @Input() slug!: string;

  protected readonly activeTab = signal<'material' | 'blocker'>('material');
  protected readonly loading = signal(false);

  protected readonly summary = computed<ReportSummary | undefined>(
    () => this.reports.summaries()[this.slug],
  );

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['slug'] && this.slug) {
      this.loading.set(true);
      this.reports.loadSummary(this.slug).subscribe({
        next: () => this.loading.set(false),
        error: (response) => {
          this.loading.set(false);
          this.notifications.showError(
            formatHttpError(response, 'Status konnte nicht geladen werden.'),
          );
        },
      });
    }
  }

  protected setTab(tab: 'material' | 'blocker'): void {
    this.activeTab.set(tab);
  }
}
