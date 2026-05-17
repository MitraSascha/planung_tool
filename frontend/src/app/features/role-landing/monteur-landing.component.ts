import { CommonModule } from '@angular/common';
import { Component, computed, inject, input, OnChanges, SimpleChanges } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { DailyReportRead, ProjectOutputFile, ProjectRead } from '../../core/models';
import { AuthService } from '../../core/services/auth.service';
import { ProjectService } from '../../core/services/project.service';
import { ReportsService } from '../../core/services/reports.service';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { AuthedUrlPipe } from '../../shared/pipes/authed-url.pipe';
import { formatDate, inferDocumentType, reportStatusLabel, sortDocumentsFormFirst } from '../../shared/utils/format';

const MONTEUR_FOLDERS = ['01_Monteur', '05_Allgemein'];

@Component({
  selector: 'app-monteur-landing',
  imports: [CommonModule, RouterLink, AuthedUrlPipe, EmptyStateComponent],
  templateUrl: './monteur-landing.component.html',
  styleUrl: './landing-sections.scss',
})
export class MonteurLandingComponent implements OnChanges {
  private readonly auth = inject(AuthService);
  private readonly projectService = inject(ProjectService);
  private readonly reports = inject(ReportsService);
  private readonly router = inject(Router);

  readonly project = input.required<ProjectRead>();

  protected readonly currentUser = this.auth.currentUser;
  protected readonly outputsByProject = this.projectService.outputs;
  protected readonly dailyReportsByProject = this.reports.dailyReports;

  protected readonly formatDate = formatDate;
  protected readonly reportStatusLabel = reportStatusLabel;
  protected readonly inferDocumentType = inferDocumentType;

  protected readonly outputs = computed<ProjectOutputFile[]>(() => {
    const all = this.outputsByProject()[this.project().slug]?.files ?? [];
    const filtered = all.filter((f) => MONTEUR_FOLDERS.some((p) => f.path.startsWith(p + '/')));
    return sortDocumentsFormFirst(filtered);
  });

  protected readonly myDailyReports = computed<DailyReportRead[]>(() => {
    const user = this.currentUser();
    if (!user) return [];
    const all = this.dailyReportsByProject()[this.project().slug] ?? [];
    return all
      .filter((r) => r.user_id === user.id)
      .slice()
      .sort((a, b) => (a.report_date < b.report_date ? 1 : -1))
      .slice(0, 5);
  });

  ngOnChanges(changes: SimpleChanges): void {
    if ('project' in changes) {
      const slug = this.project().slug;
      this.projectService.loadOutputs(slug).subscribe({ error: () => undefined });
      this.reports.loadDailyReports(slug).subscribe({ error: () => undefined });
    }
  }

  protected startDailyReport(): void {
    this.router.navigate(['/projects', this.project().slug, 'reports', 'daily', 'new']);
  }
}
