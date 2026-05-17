import { CommonModule } from '@angular/common';
import { Component, Input, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { ReportStatus, WeeklyReportForm } from '../../../core/models';
import { NotificationService } from '../../../core/services/notification.service';
import { ReportsService } from '../../../core/services/reports.service';
import { formatHttpError } from '../../../core/services/error-format';
import { weekEndIso, weekStartIso } from '../../../shared/utils/format';

@Component({
  selector: 'app-weekly-report-form',
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './weekly-report-form.component.html',
  styleUrl: './weekly-report-form.component.scss',
})
export class WeeklyReportFormComponent {
  private readonly reports = inject(ReportsService);
  private readonly notifications = inject(NotificationService);
  private readonly router = inject(Router);

  @Input() slug!: string;

  protected readonly submitting = signal(false);
  protected readonly drafting = signal(false);

  protected form: WeeklyReportForm = this.defaultForm();

  protected canDraft(): boolean {
    return !!this.form.week_start && !!this.form.week_end && !this.drafting();
  }

  protected requestDraft(): void {
    if (!this.canDraft()) {
      return;
    }
    this.notifications.clear();
    this.drafting.set(true);
    this.reports
      .draftWeeklyReport(this.slug, {
        week_start: this.form.week_start,
        week_end: this.form.week_end,
      })
      .subscribe({
        next: (draft) => {
          this.drafting.set(false);
          this.form = {
            ...this.form,
            status: (draft.status as ReportStatus) ?? this.form.status,
            summary: draft.summary ?? '',
            next_week_plan: draft.next_week_plan ?? '',
            manpower_notes: draft.manpower_notes ?? '',
            material_notes: draft.material_notes ?? '',
            risks: draft.risks ?? '',
          };
          this.notifications.showMessage('Entwurf generiert. Bitte prüfen und ggf. anpassen.');
        },
        error: (response) => {
          this.drafting.set(false);
          this.notifications.showError(
            formatHttpError(response, 'Entwurf konnte nicht generiert werden.'),
          );
        },
      });
  }

  protected setStatus(status: ReportStatus): void {
    this.form.status = status;
  }

  protected submit(): void {
    if (this.submitting()) {
      return;
    }
    this.notifications.clear();
    this.submitting.set(true);
    this.reports.submitWeeklyReport(this.slug, this.form).subscribe({
      next: () => {
        this.submitting.set(false);
        this.notifications.showMessage('Wochenbericht gespeichert.');
        this.reports.loadWeeklyReports(this.slug).subscribe({ error: () => undefined });
        this.reports.loadSummary(this.slug).subscribe({ error: () => undefined });
        this.router.navigate(['/projects', this.slug, 'reports', 'weekly']);
      },
      error: (response) => {
        this.submitting.set(false);
        this.notifications.showError(
          formatHttpError(response, 'Wochenbericht konnte nicht gespeichert werden.'),
        );
      },
    });
  }

  private defaultForm(): WeeklyReportForm {
    return {
      week_start: weekStartIso(),
      week_end: weekEndIso(),
      status: 'green',
      summary: '',
      next_week_plan: '',
      manpower_notes: '',
      material_notes: '',
      risks: '',
    };
  }
}
