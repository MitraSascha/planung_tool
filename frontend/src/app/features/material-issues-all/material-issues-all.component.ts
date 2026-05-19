import { CommonModule } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { MaterialIssueRead, ProcurementStatus } from '../../core/models';
import { NotificationService } from '../../core/services/notification.service';
import { ReportsService } from '../../core/services/reports.service';
import { formatHttpError } from '../../core/services/error-format';

/**
 * Bündel-View aller Materialmeldungen (Issue #1).
 *
 * - Listet alle Issues über alle für den User sichtbaren Projekte hinweg.
 * - Click auf eine Zeile toggelt zwischen ``offen`` und ``angekommen`` —
 *   visuell durchgestrichen wenn ``angekommen``.
 * - Backend sendet Push-Notifications an Lead-Rollen, sobald ein Monteur
 *   eine neue Meldung anlegt (siehe push_hooks._handle_material_issue_async).
 */
@Component({
  selector: 'app-material-issues-all',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './material-issues-all.component.html',
  styleUrl: './material-issues-all.component.scss',
})
export class MaterialIssuesAllComponent implements OnInit {
  private readonly reports = inject(ReportsService);
  private readonly notifications = inject(NotificationService);

  protected readonly issues = signal<MaterialIssueRead[]>([]);
  protected readonly busy = signal<Record<number, boolean>>({});
  protected readonly hideDone = signal(false);
  protected readonly filterPriority = signal<string>('all');
  protected readonly loading = signal(true);

  protected readonly visibleIssues = computed(() => {
    const all = this.issues();
    const hide = this.hideDone();
    const prio = this.filterPriority();
    return all.filter((i) => {
      if (hide && i.procurement_status === 'angekommen') return false;
      if (prio !== 'all' && i.priority !== prio) return false;
      return true;
    });
  });

  protected readonly stats = computed(() => {
    const all = this.issues();
    const open = all.filter((i) => i.procurement_status !== 'angekommen').length;
    const done = all.length - open;
    const urgent = all.filter(
      (i) => i.priority === 'urgent' && i.procurement_status !== 'angekommen',
    ).length;
    return { total: all.length, open, done, urgent };
  });

  ngOnInit(): void {
    this.reload();
  }

  protected reload(): void {
    this.loading.set(true);
    this.reports.loadAllMaterialIssues().subscribe({
      next: (rows) => {
        this.issues.set(rows);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.notifications.showError(
          formatHttpError(err, 'Materialmeldungen konnten nicht geladen werden.'),
        );
      },
    });
  }

  /** Toggle: offen ↔ angekommen. Andere Zwischenstufen (bestellt/unterwegs)
   *  werden beim Toggle zu ``angekommen`` durchgereicht — wer den Stepper
   *  fein-granular bedienen will, geht in die Projekt-Open-Points-Page. */
  protected toggleDone(issue: MaterialIssueRead): void {
    const next: ProcurementStatus =
      issue.procurement_status === 'angekommen' ? 'offen' : 'angekommen';
    this.busy.update((b) => ({ ...b, [issue.id]: true }));
    this.reports
      .updateMaterialIssueProcurement(issue.project_slug, issue.id, {
        procurement_status: next,
      })
      .subscribe({
        next: (updated) => {
          this.issues.update((all) => all.map((r) => (r.id === updated.id ? updated : r)));
          this.busy.update((b) => {
            const copy = { ...b };
            delete copy[issue.id];
            return copy;
          });
        },
        error: (err) => {
          this.busy.update((b) => {
            const copy = { ...b };
            delete copy[issue.id];
            return copy;
          });
          this.notifications.showError(
            formatHttpError(err, 'Status konnte nicht geändert werden.'),
          );
        },
      });
  }

  protected toggleHideDone(): void {
    this.hideDone.update((v) => !v);
  }

  protected setPriorityFilter(value: string): void {
    this.filterPriority.set(value);
  }

  protected priorityLabel(p: string | null | undefined): string {
    return (
      {
        low: 'niedrig',
        normal: 'normal',
        high: 'hoch',
        urgent: 'dringend',
      } as Record<string, string>
    )[p ?? 'normal'] || (p ?? '');
  }

  protected procurementLabel(s: ProcurementStatus | string): string {
    return (
      {
        offen: 'Offen',
        bestellt: 'Bestellt',
        unterwegs: 'Unterwegs',
        angekommen: 'Angekommen',
      } as Record<string, string>
    )[s] || s;
  }

  protected formatDate(iso: string | null | undefined): string {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: '2-digit' });
  }

  protected trackById(_: number, row: MaterialIssueRead): number {
    return row.id;
  }
}
