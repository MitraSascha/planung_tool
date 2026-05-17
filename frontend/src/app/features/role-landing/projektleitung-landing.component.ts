import { CommonModule } from '@angular/common';
import { Component, computed, inject, input, OnChanges, SimpleChanges } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ProjectOutputFile, ProjectRead, ReportSummary } from '../../core/models';
import { ProjectService } from '../../core/services/project.service';
import { ReportsService } from '../../core/services/reports.service';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { AuthedUrlPipe } from '../../shared/pipes/authed-url.pipe';
import { inferDocumentType, sortDocumentsFormFirst, statusLabel } from '../../shared/utils/format';

@Component({
  selector: 'app-projektleitung-landing',
  imports: [CommonModule, RouterLink, AuthedUrlPipe, EmptyStateComponent],
  templateUrl: './projektleitung-landing.component.html',
  styleUrl: './landing-sections.scss',
})
export class ProjektleitungLandingComponent implements OnChanges {
  private readonly projectService = inject(ProjectService);
  private readonly reports = inject(ReportsService);

  readonly project = input.required<ProjectRead>();
  readonly isAdmin = input<boolean>(false);

  protected readonly outputsByProject = this.projectService.outputs;
  protected readonly summariesByProject = this.reports.summaries;
  protected readonly generationRunsByProject = this.projectService.generationRuns;

  protected readonly statusLabel = statusLabel;
  protected readonly inferDocumentType = inferDocumentType;

  protected readonly outputs = computed<ProjectOutputFile[]>(() => {
    const files = this.outputsByProject()[this.project().slug]?.files ?? [];
    return sortDocumentsFormFirst(files);
  });

  protected readonly summary = computed<ReportSummary | null>(() => {
    return this.summariesByProject()[this.project().slug] ?? null;
  });

  protected readonly trafficLight = computed<'green' | 'yellow' | 'red'>(() => {
    const s = this.summary();
    if (!s) return 'green';
    if (s.status_red > 0 || s.blockers_open > 0) return 'red';
    if (s.status_yellow > 0 || s.material_issues_open > 0) return 'yellow';
    return 'green';
  });

  ngOnChanges(changes: SimpleChanges): void {
    if ('project' in changes) {
      const slug = this.project().slug;
      this.projectService.loadOutputs(slug).subscribe({ error: () => undefined });
      this.reports.loadSummary(slug).subscribe({ error: () => undefined });
    }
  }
}
