import { CommonModule } from '@angular/common';
import { Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ProjectService } from '../../core/services/project.service';
import { ReportsService } from '../../core/services/reports.service';
import { AuthService } from '../../core/services/auth.service';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';

/** „Welcome / Start"-Screen unter `/`.
 *
 *  Ersetzt den frueheren Stat-Card-Dashboard-Aufbau: die eigentliche
 *  Portfolio-Analyse liegt jetzt unter `/analyses` (Projekt-Dashboard).
 *  Diese Seite ist bewusst schlank — Welcome-Hero, rollen-abhaengige
 *  Quick-CTAs und eine kompakte „Meine aktuellen Projekte"-Liste. */
@Component({
  selector: 'app-overview',
  imports: [CommonModule, RouterLink, EmptyStateComponent],
  templateUrl: './overview.component.html',
  styleUrl: './overview.component.scss',
})
export class OverviewComponent {
  private readonly projectService = inject(ProjectService);
  private readonly reports = inject(ReportsService);
  private readonly auth = inject(AuthService);

  protected readonly currentUser = this.auth.currentUser;
  protected readonly projects = this.projectService.projects;
  protected readonly summaries = this.reports.summaries;

  protected readonly readyCount = computed(
    () => this.projects().filter((project) => project.ready_for_generation).length,
  );

  /** Sind wir Rolle „Bauleitung / Projektleitung / Admin"? Diese Rollen
   *  bekommen die Manager-CTAs (Projekt-Dashboard, Alle Projekte). */
  protected readonly isManager = computed<boolean>(() => {
    const role = this.currentUser()?.global_role;
    return role === 'projektleitung' || role === 'bauleitung' || role === 'admin';
  });

  /** Monteur / Obermonteur / Viewer → Baustellen-zentrische CTAs. */
  protected readonly isFieldRole = computed<boolean>(() => {
    const role = this.currentUser()?.global_role;
    return role === 'monteur' || role === 'obermonteur' || role === 'viewer';
  });

  /** Wenn der User genau einem Projekt zugeordnet ist, springen wir bei
   *  „Tagesbericht starten" direkt in dessen daily-new-Route. Bei mehreren
   *  oder keinem Projekt landet der CTA auf `/landing`, wo der Picker greift. */
  protected readonly dailyReportRoute = computed<string>(() => {
    const list = this.projects();
    if (list.length === 1) {
      return `/projects/${list[0].slug}/reports/daily/new`;
    }
    return '/landing';
  });

  /** Klar lesbares Label der globalen Rolle fuer das Welcome-Badge. */
  protected readonly roleLabel = computed<string>(() => {
    const role = this.currentUser()?.global_role ?? '';
    const labels: Record<string, string> = {
      admin: 'Admin',
      projektleitung: 'Projektleitung',
      bauleitung: 'Bauleitung',
      obermonteur: 'Obermonteur',
      monteur: 'Monteur',
      viewer: 'Viewer',
    };
    return labels[role] ?? role;
  });

  /** Ampel-Status pro Projekt aus den Summaries — fuer den Punkt vor
   *  dem Projekteintrag. */
  protected projectStatusColor(slug: string): 'red' | 'yellow' | 'green' {
    const summary = this.summaries()[slug];
    if (!summary) return 'green';
    if ((summary.status_red ?? 0) > 0) return 'red';
    if ((summary.status_yellow ?? 0) > 0) return 'yellow';
    return 'green';
  }

  constructor() {
    if (this.auth.isAuthenticated()) {
      this.projectService.list().subscribe({
        next: (projects) => {
          for (const project of projects) {
            this.reports.loadSummary(project.slug).subscribe({ error: () => undefined });
          }
        },
        error: () => undefined,
      });
    }
  }
}
