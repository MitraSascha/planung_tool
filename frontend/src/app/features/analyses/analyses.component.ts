import { CommonModule } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import {
  PortfolioAnalytics,
  ProjectAnalytics,
} from '../../core/models';
import { AnalyticsService } from '../../core/services/analytics.service';
import { ProjectService } from '../../core/services/project.service';
import { NotificationService } from '../../core/services/notification.service';
import { formatHttpError } from '../../core/services/error-format';

interface ProjectListItem {
  slug: string;
  name: string;
  status: string;
}

@Component({
  selector: 'app-analyses',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './analyses.component.html',
  styleUrl: './analyses.component.scss',
})
export class AnalysesComponent implements OnInit {
  private readonly analytics = inject(AnalyticsService);
  private readonly projectService = inject(ProjectService);
  private readonly notifications = inject(NotificationService);

  protected readonly busy = signal(false);
  protected readonly portfolio = signal<PortfolioAnalytics | null>(null);
  protected readonly projects = signal<ProjectListItem[]>([]);
  protected readonly selectedProjectSlug = signal<string>('');
  protected readonly projectAnalytics = signal<ProjectAnalytics | null>(null);
  protected readonly weeksBack = signal<number>(4);

  protected readonly statusRatio = computed(() => {
    const pa = this.projectAnalytics();
    if (!pa || pa.daily_status.total === 0) return null;
    return {
      green: Math.round((pa.daily_status.green / pa.daily_status.total) * 100),
      yellow: Math.round((pa.daily_status.yellow / pa.daily_status.total) * 100),
      red: Math.round((pa.daily_status.red / pa.daily_status.total) * 100),
    };
  });

  protected readonly hoursDelta = computed(() => {
    const pa = this.projectAnalytics();
    if (!pa) return 0;
    return Math.round((pa.hours_total_ist - pa.hours_total_soll) * 10) / 10;
  });

  ngOnInit(): void {
    this.loadPortfolio();
    this.projectService.list().subscribe({
      next: (list) => {
        const items = (list || []).map((p: any) => ({
          slug: p.slug, name: p.name, status: p.status,
        })) as ProjectListItem[];
        this.projects.set(items);
        if (items.length > 0) {
          this.selectedProjectSlug.set(items[0].slug);
          this.loadProject(items[0].slug);
        }
      },
      error: () => undefined,
    });
  }

  protected loadPortfolio(): void {
    this.busy.set(true);
    this.analytics.portfolio().subscribe({
      next: (p) => { this.portfolio.set(p); this.busy.set(false); },
      error: (err) => {
        this.busy.set(false);
        this.notifications.showError(formatHttpError(err, 'Portfolio konnte nicht geladen werden.'));
      },
    });
  }

  protected onProjectChange(slug: string): void {
    this.selectedProjectSlug.set(slug);
    this.loadProject(slug);
  }

  protected onWeeksChange(weeks: number): void {
    this.weeksBack.set(weeks);
    const slug = this.selectedProjectSlug();
    if (slug) this.loadProject(slug);
  }

  private loadProject(slug: string): void {
    this.busy.set(true);
    this.analytics.project(slug, this.weeksBack()).subscribe({
      next: (pa) => { this.projectAnalytics.set(pa); this.busy.set(false); },
      error: (err) => {
        this.busy.set(false);
        this.notifications.showError(formatHttpError(err, 'Projekt-Analytics konnte nicht geladen werden.'));
      },
    });
  }

  protected formatEur(value: number | null | undefined): string {
    if (value == null) return '–';
    return new Intl.NumberFormat('de-DE', {
      style: 'currency', currency: 'EUR', maximumFractionDigits: 0,
    }).format(value);
  }

  protected formatNum(value: number | null | undefined, digits = 1): string {
    if (value == null) return '–';
    return new Intl.NumberFormat('de-DE', { maximumFractionDigits: digits }).format(value);
  }

  protected percent(part: number, whole: number): number {
    if (!whole) return 0;
    return Math.round((part / whole) * 100);
  }

  protected severityColor(sev: string): string {
    return { high: '#b22424', critical: '#b22424', medium: '#8a6310', low: '#5a6b78' }[sev] || '#5a6b78';
  }
}
