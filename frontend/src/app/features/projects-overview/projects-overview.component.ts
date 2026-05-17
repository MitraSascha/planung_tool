import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Component, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { AnomalyRead, ProjectRead, ReportSummary } from '../../core/models';
import { AuthService } from '../../core/services/auth.service';
import { ProjectService } from '../../core/services/project.service';
import { ReportsService } from '../../core/services/reports.service';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { statusLabel } from '../../shared/utils/format';

type TrafficLight = 'green' | 'yellow' | 'red' | 'unknown';

interface OverviewRow {
  project: ProjectRead;
  summary: ReportSummary | null;
  trafficLight: TrafficLight;
  anomalyCount: number;
}

@Component({
  selector: 'app-projects-overview',
  imports: [CommonModule, FormsModule, EmptyStateComponent],
  templateUrl: './projects-overview.component.html',
  styleUrl: './projects-overview.component.scss',
})
export class ProjectsOverviewComponent {
  private readonly auth = inject(AuthService);
  private readonly projectService = inject(ProjectService);
  private readonly reports = inject(ReportsService);
  private readonly router = inject(Router);

  protected readonly projects = this.projectService.projects;
  protected readonly summaries = this.reports.summaries;
  protected readonly statusLabel = statusLabel;
  protected readonly loadingSummaries = signal<boolean>(false);
  protected readonly anomalyCounts = signal<Record<string, number>>({});

  protected statusFilter: string = 'all';
  protected onlyBlockers = false;
  protected onlyAtRisk = false;
  protected search = '';
  protected readonly searchSignal = signal<string>('');
  protected readonly statusFilterSignal = signal<string>('all');
  protected readonly onlyBlockersSignal = signal<boolean>(false);
  protected readonly onlyAtRiskSignal = signal<boolean>(false);

  protected readonly rows = computed<OverviewRow[]>(() => {
    const summaries = this.summaries();
    const counts = this.anomalyCounts();
    return this.projects().map((project) => {
      const summary = summaries[project.slug] ?? null;
      return {
        project,
        summary,
        trafficLight: this.computeTrafficLight(summary),
        anomalyCount: counts[project.slug] ?? 0,
      };
    });
  });

  protected readonly filteredRows = computed<OverviewRow[]>(() => {
    const search = this.searchSignal().trim().toLowerCase();
    const status = this.statusFilterSignal();
    const blockersOnly = this.onlyBlockersSignal();
    const atRiskOnly = this.onlyAtRiskSignal();
    return this.rows().filter((row) => {
      if (status !== 'all' && row.project.status !== status) return false;
      if (blockersOnly && (row.summary?.blockers_open ?? 0) === 0) return false;
      if (atRiskOnly && row.trafficLight !== 'red' && row.trafficLight !== 'yellow') return false;
      if (search.length > 0) {
        const haystack = [
          row.project.name,
          row.project.slug,
          row.project.address ?? '',
          row.project.responsible ?? '',
        ]
          .join(' ')
          .toLowerCase();
        if (!haystack.includes(search)) return false;
      }
      return true;
    });
  });

  protected readonly totalCount = computed(() => this.projects().length);
  protected readonly redCount = computed(() => this.rows().filter((r) => r.trafficLight === 'red').length);
  protected readonly yellowCount = computed(() => this.rows().filter((r) => r.trafficLight === 'yellow').length);
  protected readonly blockerSum = computed(() =>
    this.rows().reduce((acc, r) => acc + (r.summary?.blockers_open ?? 0), 0),
  );

  constructor() {
    if (this.auth.isAuthenticated()) {
      this.loadingSummaries.set(true);
      this.projectService.list().subscribe({
        next: (projects) => {
          let pending = projects.length;
          if (pending === 0) {
            this.loadingSummaries.set(false);
            this.loadAnomalyCounts();
            return;
          }
          for (const project of projects) {
            this.reports.loadSummary(project.slug).subscribe({
              next: () => {
                pending -= 1;
                if (pending <= 0) this.loadingSummaries.set(false);
              },
              error: () => {
                pending -= 1;
                if (pending <= 0) this.loadingSummaries.set(false);
              },
            });
          }
          this.loadAnomalyCounts();
        },
        error: () => this.loadingSummaries.set(false),
      });
    }
  }

  private loadAnomalyCounts(): void {
    // One global call, then bucket by project_slug — cheaper than N round-trips.
    this.reports.listAnomalies().subscribe({
      next: (anomalies: AnomalyRead[]) => {
        const counts: Record<string, number> = {};
        for (const a of anomalies ?? []) {
          counts[a.project_slug] = (counts[a.project_slug] ?? 0) + 1;
        }
        this.anomalyCounts.set(counts);
      },
      error: () => undefined,
    });
  }

  protected onSearch(value: string): void {
    this.search = value;
    this.searchSignal.set(value);
  }

  protected onStatusFilter(value: string): void {
    this.statusFilter = value;
    this.statusFilterSignal.set(value);
  }

  protected onBlockersToggle(value: boolean): void {
    this.onlyBlockers = value;
    this.onlyBlockersSignal.set(value);
  }

  protected onAtRiskToggle(value: boolean): void {
    this.onlyAtRisk = value;
    this.onlyAtRiskSignal.set(value);
  }

  protected openProject(slug: string): void {
    this.router.navigate(['/projects', slug, 'role']);
  }

  private computeTrafficLight(summary: ReportSummary | null): TrafficLight {
    if (!summary) return 'unknown';
    if (summary.status_red > 0 || summary.blockers_open > 0) return 'red';
    if (summary.status_yellow > 0 || summary.material_issues_open > 0) return 'yellow';
    return 'green';
  }
}
