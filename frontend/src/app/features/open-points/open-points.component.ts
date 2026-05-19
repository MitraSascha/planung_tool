import { CommonModule } from '@angular/common';
import { Component, Input, OnChanges, OnInit, SimpleChanges, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { BlockerRead, IssueStatusUpdate, MaterialIssueRead, ProcurementStatus, ReportSummary } from '../../core/models';
import { ReportsService } from '../../core/services/reports.service';
import { NotificationService } from '../../core/services/notification.service';
import { formatHttpError } from '../../core/services/error-format';

type IssueStatusValue = IssueStatusUpdate['status'];

interface ProcurementStep {
  value: ProcurementStatus;
  label: string;
  icon: string;
  index: number;
}

@Component({
  selector: 'app-open-points',
  imports: [CommonModule, RouterLink],
  templateUrl: './open-points.component.html',
  styleUrl: './open-points.component.scss',
})
export class OpenPointsComponent implements OnChanges, OnInit {
  private readonly reports = inject(ReportsService);
  private readonly notifications = inject(NotificationService);
  private readonly route = inject(ActivatedRoute);

  @Input() slug!: string;

  protected readonly activeTab = signal<'material' | 'blocker'>('material');

  ngOnInit(): void {
    // Deep-Link: ?tab=blocker bzw. ?tab=material setzt direkt den Reiter,
    // damit Karten aus dem Projektüberblick zur richtigen Liste springen.
    this.route.queryParamMap.subscribe((params) => {
      const tab = params.get('tab');
      if (tab === 'material' || tab === 'blocker') {
        this.activeTab.set(tab);
      }
    });
  }
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

  /** Stepper-Stufen für den Beschaffungs-Workflow (Material). */
  protected readonly procurementSteps: ProcurementStep[] = [
    { value: 'offen', label: 'Offen', icon: '📝', index: 0 },
    { value: 'bestellt', label: 'Bestellt', icon: '📦', index: 1 },
    { value: 'unterwegs', label: 'Unterwegs', icon: '🚚', index: 2 },
    { value: 'angekommen', label: 'Angekommen', icon: '✅', index: 3 },
  ];

  /** Index der aktuell aktiven Stepper-Stufe einer Materialmeldung. */
  protected procurementIndex(issue: MaterialIssueRead): number {
    const found = this.procurementSteps.find((s) => s.value === issue.procurement_status);
    return found?.index ?? 0;
  }

  /** Audit-Info pro Stufe (für das Mini-Label unter dem Stepper). */
  protected stepAuditInfo(issue: MaterialIssueRead, step: ProcurementStep): { user: string; at: string } | null {
    let at: string | null | undefined;
    let user: string | null | undefined;
    switch (step.value) {
      case 'bestellt':
        at = issue.ordered_at;
        user = issue.ordered_by_username;
        break;
      case 'unterwegs':
        at = issue.shipped_at;
        user = issue.shipped_by_username;
        break;
      case 'angekommen':
        at = issue.arrived_at;
        user = issue.arrived_by_username;
        break;
      default:
        return null;
    }
    if (!at) return null;
    return { user: user ?? '—', at };
  }

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

  /** Stepper-Klick: setzt eine Beschaffungs-Stufe. No-op, wenn bereits aktiv. */
  protected onProcurementStepClick(issue: MaterialIssueRead, step: ProcurementStep): void {
    if (issue.procurement_status === step.value) return;
    this.pendingId.set(issue.id);
    this.reports
      .updateMaterialIssueProcurement(this.slug, issue.id, { procurement_status: step.value })
      .subscribe({
        next: () => {
          this.pendingId.set(null);
          this.reports.loadSummary(this.slug).subscribe({ error: () => undefined });
        },
        error: (response) => {
          this.pendingId.set(null);
          this.notifications.showError(
            formatHttpError(response, 'Beschaffungs-Status konnte nicht gespeichert werden.'),
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
