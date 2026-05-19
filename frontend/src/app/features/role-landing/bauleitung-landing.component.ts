import { CommonModule } from '@angular/common';
import { Component, computed, inject, input, OnChanges, SimpleChanges } from '@angular/core';
import { RouterLink } from '@angular/router';

import { DailyReportRead, ProjectOutputFile, ProjectRead, ReportSummary } from '../../core/models';
import { ProjectService } from '../../core/services/project.service';
import { ReportsService } from '../../core/services/reports.service';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { AuthedUrlPipe } from '../../shared/pipes/authed-url.pipe';
import { formatDate, inferDocumentType, reportStatusLabel, sortDocumentsFormFirst } from '../../shared/utils/format';

const BAULEITUNG_FOLDERS = ['03_Bauleitung', '05_Allgemein'];

@Component({
  selector: 'app-bauleitung-landing',
  imports: [CommonModule, RouterLink, AuthedUrlPipe, EmptyStateComponent],
  templateUrl: './bauleitung-landing.component.html',
  styleUrl: './landing-sections.scss',
})
export class BauleitungLandingComponent implements OnChanges {
  private readonly projectService = inject(ProjectService);
  private readonly reports = inject(ReportsService);

  readonly project = input.required<ProjectRead>();

  protected readonly outputsByProject = this.projectService.outputs;
  protected readonly dailyReportsByProject = this.reports.dailyReports;
  protected readonly summariesByProject = this.reports.summaries;

  protected readonly formatDate = formatDate;
  protected readonly reportStatusLabel = reportStatusLabel;
  protected readonly inferDocumentType = inferDocumentType;

  protected readonly outputs = computed<ProjectOutputFile[]>(() => {
    const all = this.outputsByProject()[this.project().slug]?.files ?? [];
    const filtered = all.filter((f) => BAULEITUNG_FOLDERS.some((p) => f.path.startsWith(p + '/')));
    return sortDocumentsFormFirst(filtered);
  });

  protected readonly recentReports = computed<DailyReportRead[]>(() => {
    const all = this.dailyReportsByProject()[this.project().slug] ?? [];
    return all
      .slice()
      .sort((a, b) => (a.report_date < b.report_date ? 1 : -1))
      .slice(0, 10);
  });

  protected readonly summary = computed<ReportSummary | null>(() => {
    return this.summariesByProject()[this.project().slug] ?? null;
  });

  /** Gleiche Ampel-Logik wie in projektleitung-landing — Bauleitung muss
   *  Probleme genauso früh sehen wie die Projektleitung. */
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
      this.reports.loadDailyReports(slug).subscribe({ error: () => undefined });
      this.reports.loadSummary(slug).subscribe({ error: () => undefined });
    }
  }
}
