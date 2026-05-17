import { CommonModule } from '@angular/common';
import { Component, Input, OnChanges, OnInit, SimpleChanges, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { AnomalyRead } from '../../core/models';
import { ReportsService } from '../../core/services/reports.service';
import { NotificationService } from '../../core/services/notification.service';
import { formatHttpError } from '../../core/services/error-format';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';

interface ProjectGroup {
  projectSlug: string;
  anomalies: AnomalyRead[];
}

@Component({
  selector: 'app-anomalies',
  imports: [CommonModule, RouterLink, EmptyStateComponent],
  templateUrl: './anomalies.component.html',
  styleUrl: './anomalies.component.scss',
})
export class AnomaliesComponent implements OnChanges, OnInit {
  private readonly reports = inject(ReportsService);
  private readonly notifications = inject(NotificationService);
  private readonly router = inject(Router);

  @Input() slug?: string;

  protected readonly loading = signal(false);
  protected readonly anomalies = signal<AnomalyRead[]>([]);

  protected readonly grouped = computed<ProjectGroup[]>(() => {
    const map = new Map<string, AnomalyRead[]>();
    for (const anomaly of this.anomalies()) {
      const bucket = map.get(anomaly.project_slug) ?? [];
      bucket.push(anomaly);
      map.set(anomaly.project_slug, bucket);
    }
    return Array.from(map.entries())
      .map(([projectSlug, anomalies]) => ({ projectSlug, anomalies }))
      .sort((a, b) => a.projectSlug.localeCompare(b.projectSlug));
  });

  protected readonly criticalCount = computed(
    () => this.anomalies().filter((a) => a.severity === 'critical').length,
  );
  protected readonly warningCount = computed(
    () => this.anomalies().filter((a) => a.severity === 'warning').length,
  );

  private initialLoadDone = false;

  ngOnChanges(changes: SimpleChanges): void {
    if ('slug' in changes) {
      this.initialLoadDone = true;
      this.load();
    }
  }

  ngOnInit(): void {
    // Triggered on the "/anomalies" route (no :slug param).
    if (!this.initialLoadDone) {
      this.load();
    }
  }

  protected load(): void {
    this.loading.set(true);
    this.reports.listAnomalies(this.slug).subscribe({
      next: (data) => {
        this.anomalies.set(data ?? []);
        this.loading.set(false);
      },
      error: (response) => {
        this.loading.set(false);
        this.notifications.showError(
          formatHttpError(response, 'Anomalien konnten nicht geladen werden.'),
        );
      },
    });
  }

  protected severityLabel(severity: string): string {
    switch (severity) {
      case 'critical':
        return 'Kritisch';
      case 'warning':
        return 'Warnung';
      case 'info':
        return 'Info';
      default:
        return severity;
    }
  }

  protected kindLabel(kind: string): string {
    switch (kind) {
      case 'consecutive_red':
        return 'Status mehrfach rot';
      case 'recurring_material':
        return 'Wiederkehrendes Material';
      case 'stale_blocker':
        return 'Alter Blocker';
      default:
        return kind;
    }
  }

  protected openTarget(anomaly: AnomalyRead): void {
    const target = this.targetRoute(anomaly);
    if (target) {
      this.router.navigate(target);
    }
  }

  private targetRoute(anomaly: AnomalyRead): unknown[] | null {
    if (!anomaly.project_slug) return null;
    switch (anomaly.kind) {
      case 'consecutive_red':
        return ['/projects', anomaly.project_slug, 'reports', 'daily'];
      case 'recurring_material':
        return ['/projects', anomaly.project_slug, 'open-points'];
      case 'stale_blocker':
        return ['/projects', anomaly.project_slug, 'open-points'];
      default:
        return ['/projects', anomaly.project_slug];
    }
  }
}
