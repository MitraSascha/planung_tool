import { CommonModule } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import {
  ProjectOutputFile,
  ProjectRead,
  TERMINAL_RUN_STATUSES,
} from '../../core/models';
import { AuthService } from '../../core/services/auth.service';
import { NotificationService } from '../../core/services/notification.service';
import { ProjectService } from '../../core/services/project.service';
import { formatHttpError } from '../../core/services/error-format';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { RunProgressComponent } from '../../shared/components/run-progress/run-progress.component';
import {
  ALLOWED_UPLOAD_SUFFIXES,
  formatDateTime,
  formatFileSize,
  isAllowedUploadFile,
  statusLabel,
} from '../../shared/utils/format';

@Component({
  selector: 'app-project-outputs',
  imports: [CommonModule, RouterLink, RunProgressComponent, EmptyStateComponent],
  templateUrl: './project-outputs.component.html',
  styleUrl: './project-outputs.component.scss',
})
export class ProjectOutputsComponent {
  private readonly projectService = inject(ProjectService);
  private readonly notifications = inject(NotificationService);
  private readonly auth = inject(AuthService);

  protected readonly projects = this.projectService.projects;
  protected readonly outputs = this.projectService.outputs;
  protected readonly generationRuns = this.projectService.generationRuns;

  protected readonly allowedUploadTypes = ALLOWED_UPLOAD_SUFFIXES.join(',');
  protected readonly statusLabel = statusLabel;
  protected readonly formatDateTime = formatDateTime;
  protected readonly formatFileSize = formatFileSize;

  protected readonly selectedUploadNames = signal<Record<string, string[]>>({});
  protected readonly uploadingSlug = signal<string | null>(null);
  protected readonly generatingSlug = signal<string | null>(null);
  protected readonly outputsLoadingSlug = signal<string | null>(null);

  private readonly selectedFiles = new Map<string, File[]>();

  constructor() {
    if (this.auth.isAuthenticated()) {
      this.projectService.list().subscribe({
        next: (projects) => {
          for (const project of projects) {
            if (project.status === 'published') {
              this.projectService.loadOutputs(project.slug).subscribe({ error: () => undefined });
            }
          }
        },
        error: () => undefined,
      });
    }
  }

  protected projectOutputCount(slug: string): number {
    return this.outputs()[slug]?.files.length ?? 0;
  }

  protected loadOutputs(slug: string): void {
    this.outputsLoadingSlug.set(slug);
    this.projectService.loadOutputs(slug).subscribe({
      next: () => this.outputsLoadingSlug.set(null),
      error: (response) => {
        this.outputsLoadingSlug.set(null);
        this.notifications.showError(
          formatHttpError(response, 'Ausgaben konnten nicht geladen werden.'),
        );
      },
    });
  }

  protected outputGroups(files: ProjectOutputFile[]): { folder: string; files: ProjectOutputFile[] }[] {
    const groups = new Map<string, ProjectOutputFile[]>();
    for (const file of files) {
      const folder = file.path.includes('/')
        ? file.path.slice(0, file.path.lastIndexOf('/'))
        : 'Root';
      groups.set(folder, [...(groups.get(folder) ?? []), file]);
    }
    return Array.from(groups.entries()).map(([folder, groupedFiles]) => ({
      folder,
      files: groupedFiles,
    }));
  }

  protected openOutputFile(file: ProjectOutputFile): void {
    this.projectService.fetchOutputFile(file.view_url).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        window.open(url, '_blank', 'noopener');
        window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      },
      error: (response) =>
        this.notifications.showError(
          formatHttpError(response, 'Ausgabedatei konnte nicht geoeffnet werden.'),
        ),
    });
  }

  protected onUploadSelection(slug: string, event: Event): void {
    const input = event.target as HTMLInputElement;
    const files = Array.from(input.files ?? []);
    const unsupported = files.find((file) => !isAllowedUploadFile(file));

    if (unsupported) {
      this.notifications.showError(
        `${unsupported.name} ist kein erlaubter Dateityp. Erlaubt sind CSV, PDF, XLSX und XLS.`,
      );
      input.value = '';
      this.selectedFiles.delete(slug);
      this.selectedUploadNames.update((current) => ({ ...current, [slug]: [] }));
      return;
    }

    this.selectedFiles.set(slug, files);
    this.selectedUploadNames.update((current) => ({
      ...current,
      [slug]: files.map((file) => file.name),
    }));
  }

  protected uploadFiles(slug: string): void {
    const files = this.selectedFiles.get(slug) ?? [];
    if (files.length === 0) {
      this.notifications.showError('Bitte zuerst eine oder mehrere Dateien auswaehlen.');
      return;
    }

    this.notifications.clear();
    this.uploadingSlug.set(slug);
    this.uploadNext(slug, files, 0, 0);
  }

  private uploadNext(slug: string, files: File[], index: number, succeeded: number): void {
    if (index >= files.length) {
      this.uploadingSlug.set(null);
      this.notifications.showMessage(`${succeeded} Datei(en) wurden hochgeladen.`);
      this.selectedFiles.delete(slug);
      this.selectedUploadNames.update((current) => ({ ...current, [slug]: [] }));
      this.projectService.list().subscribe({ error: () => undefined });
      return;
    }

    this.projectService.uploadFile(slug, files[index]).subscribe({
      next: () => this.uploadNext(slug, files, index + 1, succeeded + 1),
      error: (response) => {
        this.uploadingSlug.set(null);
        this.notifications.showError(
          formatHttpError(response, `${files[index].name} konnte nicht hochgeladen werden.`),
        );
      },
    });
  }

  protected runDryGenerate(slug: string): void {
    this.notifications.clear();
    this.projectService.dryRun(slug).subscribe({
      next: (response) => {
        this.notifications.showMessage('Generator-Dry-Run wurde vorbereitet.');
        this.notifications.setDryRunPrompt(response.stderr);
      },
      error: (response) =>
        this.notifications.showError(
          formatHttpError(response, 'Dry-Run konnte nicht erstellt werden.'),
        ),
    });
  }

  protected runGenerate(project: ProjectRead): void {
    if (!project.ready_for_generation) {
      this.notifications.showError(
        'Vor dem Generatorlauf bitte die offenen Punkte in der Projektkarte klären.',
      );
      return;
    }

    this.notifications.clear();
    this.generatingSlug.set(project.slug);

    this.projectService.startGeneration(project.slug).subscribe({
      next: (response) => {
        if (!response.run_id) {
          this.generatingSlug.set(null);
          this.notifications.showError(
            'Generatorlauf wurde gestartet, aber keine Run-ID wurde zurueckgegeben.',
          );
          return;
        }
        this.notifications.showMessage(
          `Generatorlauf gestartet: ${response.current_step ?? 'Wartet'} (${response.progress_current} von ${response.progress_total}).`,
        );
        this.pollRun(project.slug, response.run_id);
      },
      error: (response) => {
        this.generatingSlug.set(null);
        this.notifications.showError(
          formatHttpError(response, 'Generatorlauf konnte nicht gestartet werden.'),
        );
        this.projectService.list().subscribe({ error: () => undefined });
      },
    });
  }

  private pollRun(slug: string, runId: number): void {
    this.projectService.getRun(slug, runId).subscribe({
      next: (run) => {
        this.projectService.setGenerationRun(slug, run);
        const isDone = TERMINAL_RUN_STATUSES.includes(run.status);

        if (isDone) {
          this.generatingSlug.set(null);
          this.notifications.showMessage(
            run.status === 'completed' || run.status === 'succeeded'
              ? 'Generatorlauf abgeschlossen.'
              : 'Generatorlauf wurde mit Fehler beendet.',
          );
          this.notifications.setDryRunPrompt(
            [run.stdout, run.stderr].filter(Boolean).join('\n\n'),
          );
          this.projectService.list().subscribe({ error: () => undefined });
          this.projectService.loadOutputs(slug).subscribe({ error: () => undefined });
          return;
        }

        window.setTimeout(() => this.pollRun(slug, runId), 3000);
      },
      error: (response) => {
        this.generatingSlug.set(null);
        this.notifications.showError(
          formatHttpError(response, 'Generatorstatus konnte nicht geladen werden.'),
        );
      },
    });
  }
}
