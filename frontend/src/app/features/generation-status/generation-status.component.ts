import { CommonModule } from '@angular/common';
import { Component, Input, OnInit, computed, inject, signal } from '@angular/core';

import { ProjectRead, TERMINAL_RUN_STATUSES } from '../../core/models';
import { NotificationService } from '../../core/services/notification.service';
import { ProjectService } from '../../core/services/project.service';
import { formatHttpError } from '../../core/services/error-format';
import { statusLabel } from '../../shared/utils/format';
import { RunProgressComponent } from '../../shared/components/run-progress/run-progress.component';

@Component({
  selector: 'app-generation-status',
  imports: [CommonModule, RunProgressComponent],
  templateUrl: './generation-status.component.html',
  styleUrl: './generation-status.component.scss',
})
export class GenerationStatusComponent implements OnInit {
  private readonly projectService = inject(ProjectService);
  private readonly notifications = inject(NotificationService);

  @Input() slug!: string;

  protected readonly project = signal<ProjectRead | null>(null);
  protected readonly isGenerating = signal(false);
  protected readonly generationRuns = this.projectService.generationRuns;

  protected readonly currentRun = computed(() => this.generationRuns()[this.slug]);

  protected readonly statusLabel = statusLabel;

  ngOnInit(): void {
    this.loadProject();
  }

  protected loadProject(): void {
    this.projectService.get(this.slug).subscribe({
      next: (project) => this.project.set(project),
      error: (response) =>
        this.notifications.showError(formatHttpError(response, 'Projekt konnte nicht geladen werden.')),
    });
  }

  protected runDryGenerate(): void {
    this.notifications.clear();
    this.projectService.dryRun(this.slug).subscribe({
      next: (response) => {
        this.notifications.showMessage('Generator-Dry-Run wurde vorbereitet.');
        this.notifications.setDryRunPrompt(response.stderr);
      },
      error: (response) =>
        this.notifications.showError(formatHttpError(response, 'Dry-Run konnte nicht erstellt werden.')),
    });
  }

  protected runGenerate(): void {
    const current = this.project();
    if (!current) {
      return;
    }

    if (!current.ready_for_generation) {
      this.notifications.showError(
        'Vor dem Generatorlauf bitte die offenen Punkte in der Projektkarte klären.',
      );
      return;
    }

    this.notifications.clear();
    this.isGenerating.set(true);

    this.projectService.startGeneration(this.slug).subscribe({
      next: (response) => {
        if (!response.run_id) {
          this.isGenerating.set(false);
          this.notifications.showError(
            'Generatorlauf wurde gestartet, aber keine Run-ID wurde zurueckgegeben.',
          );
          return;
        }
        this.notifications.showMessage(
          `Generatorlauf gestartet: ${response.current_step ?? 'Wartet'} (${response.progress_current} von ${response.progress_total}).`,
        );
        this.pollRun(response.run_id);
      },
      error: (response) => {
        this.isGenerating.set(false);
        this.notifications.showError(
          formatHttpError(response, 'Generatorlauf konnte nicht gestartet werden.'),
        );
        this.loadProject();
      },
    });
  }

  private pollRun(runId: number): void {
    this.projectService.getRun(this.slug, runId).subscribe({
      next: (run) => {
        this.projectService.setGenerationRun(this.slug, run);
        const isDone = TERMINAL_RUN_STATUSES.includes(run.status);

        if (isDone) {
          this.isGenerating.set(false);
          this.notifications.showMessage(
            run.status === 'completed' || run.status === 'succeeded'
              ? 'Generatorlauf abgeschlossen.'
              : 'Generatorlauf wurde mit Fehler beendet.',
          );
          this.notifications.setDryRunPrompt(
            [run.stdout, run.stderr].filter(Boolean).join('\n\n'),
          );
          this.loadProject();
          this.projectService.loadOutputs(this.slug).subscribe({ error: () => undefined });
          return;
        }

        window.setTimeout(() => this.pollRun(runId), 3000);
      },
      error: (response) => {
        this.isGenerating.set(false);
        this.notifications.showError(
          formatHttpError(response, 'Generatorstatus konnte nicht geladen werden.'),
        );
      },
    });
  }
}
