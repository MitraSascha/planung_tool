import { CommonModule } from '@angular/common';
import { Component, Input, OnChanges, SimpleChanges, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { BlockerRead, IssueStatusUpdate, MaterialIssueRead, ReportSummary } from '../../core/models';
import { ReportsService } from '../../core/services/reports.service';
import { NotificationService } from '../../core/services/notification.service';
import { formatHttpError } from '../../core/services/error-format';

type IssueStatusValue = IssueStatusUpdate['status'];

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
  protected readonly pendingId = signal<number | null>(null);

  protected readonly summary = computed<ReportSummary | undefined>(
    () => this.reports.summaries()[this.slug],
  );

  protected readonly materialIssues = computed<MaterialIssueRead[]>(
    () => this.reports.materialIssues()[this.slug] ?? [],
  );

  protected readonly blockers = computed<BlockerRead[]>(
    () => this.reports.blockers()[this.slug] ?? [],
  );

  protected readonly statusOptions: { value: IssueStatusValue; label: string }[] = [
    { value: 'open', label: 'Offen' },
    { value: 'in_progress', label: 'In Arbeit' },
    { value: 'done', label: 'Erledigt' },
  ];

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['slug'] && this.slug) {
      this.refresh();
    }
  }

  protected setTab(tab: 'material' | 'blocker'): void {
    this.activeTab.set(tab);
  }

  protected trackById(_index: number, item: { id: number }): number {
    return item.id;
  }

  protected onMaterialStatusChange(issue: MaterialIssueRead, status: IssueStatusValue): void {
    if (status === issue.status) return;
    this.pendingId.set(issue.id);
    this.reports.updateMaterialIssueStatus(this.slug, issue.id, { status }).subscribe({
      next: () => {
        this.pendingId.set(null);
        this.reports.loadSummary(this.slug).subscribe({ error: () => undefined });
      },
      error: (response) => {
        this.pendingId.set(null);
        this.notifications.showError(
          formatHttpError(response, 'Status konnte nicht gespeichert werden.'),
        );
      },
    });
  }

  protected onBlockerStatusChange(blocker: BlockerRead, status: IssueStatusValue): void {
    if (status === blocker.status) return;
    this.pendingId.set(blocker.id);
    this.reports.updateBlockerStatus(this.slug, blocker.id, { status }).subscribe({
      next: () => {
        this.pendingId.set(null);
        this.reports.loadSummary(this.slug).subscribe({ error: () => undefined });
      },
      error: (response) => {
        this.pendingId.set(null);
        this.notifications.showError(
          formatHttpError(response, 'Status konnte nicht gespeichert werden.'),
        );
      },
    });
  }

  private refresh(): void {
    this.loading.set(true);
    let pending = 3;
    const done = () => {
      pending -= 1;
      if (pending === 0) this.loading.set(false);
    };
    const onError = (response: any, fallback: string) => {
      done();
      this.notifications.showError(formatHttpError(response, fallback));
    };

    this.reports.loadSummary(this.slug).subscribe({
      next: () => done(),
      error: (r) => onError(r, 'Status konnte nicht geladen werden.'),
    });
    this.reports.loadMaterialIssues(this.slug).subscribe({
      next: () => done(),
      error: (r) => onError(r, 'Materialmeldungen konnten nicht geladen werden.'),
    });
    this.reports.loadBlockers(this.slug).subscribe({
      next: () => done(),
      error: (r) => onError(r, 'Blocker konnten nicht geladen werden.'),
    });
  }
}
