import { CommonModule } from '@angular/common';
import { Component, computed, inject } from '@angular/core';

import { ProjectService } from '../../core/services/project.service';
import { ReportsService } from '../../core/services/reports.service';
import { AuthService } from '../../core/services/auth.service';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { statusLabel } from '../../shared/utils/format';

@Component({
  selector: 'app-overview',
  imports: [CommonModule, EmptyStateComponent],
  templateUrl: './overview.component.html',
  styleUrl: './overview.component.scss',
})
export class OverviewComponent {
  private readonly projectService = inject(ProjectService);
  private readonly reports = inject(ReportsService);
  private readonly auth = inject(AuthService);

  protected readonly projects = this.projectService.projects;
  protected readonly summaries = this.reports.summaries;
  protected readonly outputs = this.projectService.outputs;

  protected readonly readyCount = computed(
    () => this.projects().filter((project) => project.ready_for_generation).length,
  );

  protected readonly publishedCount = computed(
    () => this.projects().filter((project) => project.status === 'published').length,
  );

  protected readonly totalOutputs = computed(() =>
    Object.values(this.outputs()).reduce((total, output) => total + output.files.length, 0),
  );

  protected readonly statusLabel = statusLabel;

  constructor() {
    if (this.auth.isAuthenticated()) {
      this.projectService.list().subscribe({
        next: (projects) => {
          for (const project of projects) {
            this.reports.loadSummary(project.slug).subscribe({ error: () => undefined });
            if (project.status === 'published') {
              this.projectService.loadOutputs(project.slug).subscribe({ error: () => undefined });
            }
          }
        },
        error: () => undefined,
      });
    }
  }
}
