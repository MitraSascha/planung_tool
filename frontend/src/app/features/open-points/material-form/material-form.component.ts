import { CommonModule } from '@angular/common';
import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { MaterialIssueCreate, MaterialPriority, ProjectRead } from '../../../core/models';
import { NotificationService } from '../../../core/services/notification.service';
import { ProjectService } from '../../../core/services/project.service';
import { ReportsService } from '../../../core/services/reports.service';
import { formatHttpError } from '../../../core/services/error-format';

@Component({
  selector: 'app-material-form',
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './material-form.component.html',
  styleUrl: './material-form.component.scss',
})
export class MaterialFormComponent implements OnInit {
  private readonly reports = inject(ReportsService);
  private readonly projects = inject(ProjectService);
  private readonly notifications = inject(NotificationService);
  private readonly router = inject(Router);

  @Input() slug!: string;

  protected readonly project = signal<ProjectRead | null>(null);
  protected readonly submitting = signal(false);

  protected form: MaterialIssueCreate = {
    section_number: null,
    description: '',
    priority: 'normal',
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

  protected setPriority(priority: MaterialPriority): void {
    this.form.priority = priority;
  }

  protected submit(): void {
    if (this.submitting()) {
      return;
    }
    this.notifications.clear();
    this.submitting.set(true);
    this.reports.createMaterialIssue(this.slug, this.form).subscribe({
      next: () => {
        this.submitting.set(false);
        this.notifications.showMessage('Materialmeldung gespeichert.');
        this.reports.loadSummary(this.slug).subscribe({ error: () => undefined });
        this.router.navigate(['/projects', this.slug, 'open-points']);
      },
      error: (response) => {
        this.submitting.set(false);
        this.notifications.showError(
          formatHttpError(response, 'Materialmeldung konnte nicht gespeichert werden.'),
        );
      },
    });
  }
}
