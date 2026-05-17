import { CommonModule } from '@angular/common';
import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { BlockerCreate, BlockerSeverity, ProjectRead } from '../../../core/models';
import { NotificationService } from '../../../core/services/notification.service';
import { ProjectService } from '../../../core/services/project.service';
import { ReportsService } from '../../../core/services/reports.service';
import { formatHttpError } from '../../../core/services/error-format';

@Component({
  selector: 'app-blocker-form',
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './blocker-form.component.html',
  styleUrl: './blocker-form.component.scss',
})
export class BlockerFormComponent implements OnInit {
  private readonly reports = inject(ReportsService);
  private readonly projects = inject(ProjectService);
  private readonly notifications = inject(NotificationService);
  private readonly router = inject(Router);

  @Input() slug!: string;

  protected readonly project = signal<ProjectRead | null>(null);
  protected readonly submitting = signal(false);

  protected form: BlockerCreate = {
    section_number: null,
    description: '',
    severity: 'medium',
  };

  ngOnInit(): void {
    this.projects.get(this.slug).subscribe({
      next: (project) => this.project.set(project),
      error: (response) =>
        this.notifications.showError(
          formatHttpError(response, 'Projekt konnte nicht geladen werden.'),
        ),
    });
  }

  protected setSeverity(severity: BlockerSeverity): void {
    this.form.severity = severity;
  }

  protected submit(): void {
    if (this.submitting()) {
      return;
    }
    this.notifications.clear();
    this.submitting.set(true);
    this.reports.createBlocker(this.slug, this.form).subscribe({
      next: () => {
        this.submitting.set(false);
        this.notifications.showMessage('Blocker gespeichert.');
        this.reports.loadSummary(this.slug).subscribe({ error: () => undefined });
        this.router.navigate(['/projects', this.slug, 'open-points']);
      },
      error: (response) => {
        this.submitting.set(false);
        this.notifications.showError(
          formatHttpError(response, 'Blocker konnte nicht gespeichert werden.'),
        );
      },
    });
  }
}
