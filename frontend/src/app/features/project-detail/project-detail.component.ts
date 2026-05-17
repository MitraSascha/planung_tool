import { CommonModule } from '@angular/common';
import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ProjectRead } from '../../core/models';
import { NotificationService } from '../../core/services/notification.service';
import { ProjectService } from '../../core/services/project.service';
import { formatHttpError } from '../../core/services/error-format';
import {
  formatDateTime,
  formatFileSize,
  projectTypeLabel,
  statusLabel,
} from '../../shared/utils/format';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { HeatingDesignComponent } from '../heating-design/heating-design.component';

@Component({
  selector: 'app-project-detail',
  imports: [CommonModule, RouterLink, HeatingDesignComponent, EmptyStateComponent],
  templateUrl: './project-detail.component.html',
  styleUrl: './project-detail.component.scss',
})
export class ProjectDetailComponent implements OnInit {
  private readonly projectService = inject(ProjectService);
  private readonly notifications = inject(NotificationService);

  @Input() slug!: string;

  protected readonly project = signal<ProjectRead | null>(null);
  protected readonly outputs = this.projectService.outputs;

  protected readonly statusLabel = statusLabel;
  protected readonly projectTypeLabel = projectTypeLabel;
  protected readonly formatFileSize = formatFileSize;
  protected readonly formatDateTime = formatDateTime;

  ngOnInit(): void {
    this.reload();
  }

  protected reload(): void {
    this.projectService.get(this.slug).subscribe({
      next: (project) => {
        this.project.set(project);
        if (project.status === 'published') {
          this.projectService.loadOutputs(this.slug).subscribe({ error: () => undefined });
        }
      },
      error: (response) =>
        this.notifications.showError(formatHttpError(response, 'Projekt konnte nicht geladen werden.')),
    });
  }
}
