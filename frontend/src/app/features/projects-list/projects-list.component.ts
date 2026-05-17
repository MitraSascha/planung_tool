import { CommonModule } from '@angular/common';
import { Component, inject } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { AuthService } from '../../core/services/auth.service';
import { ProjectService } from '../../core/services/project.service';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { projectTypeLabel, statusLabel } from '../../shared/utils/format';

@Component({
  selector: 'app-projects-list',
  imports: [CommonModule, RouterLink, EmptyStateComponent],
  templateUrl: './projects-list.component.html',
  styleUrl: './projects-list.component.scss',
})
export class ProjectsListComponent {
  private readonly projectService = inject(ProjectService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly projects = this.projectService.projects;
  protected readonly statusLabel = statusLabel;
  protected readonly projectTypeLabel = projectTypeLabel;

  constructor() {
    if (this.auth.isAuthenticated()) {
      this.projectService.list().subscribe({ error: () => undefined });
    }
  }

  protected createProject(): void {
    this.router.navigate(['/projects/new']);
  }
}
