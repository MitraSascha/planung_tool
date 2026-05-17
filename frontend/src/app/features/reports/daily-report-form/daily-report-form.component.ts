import { CommonModule } from '@angular/common';
import { Component, Input, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { forkJoin, of } from 'rxjs';
import { catchError, switchMap } from 'rxjs/operators';

import { DailyReportForm, ProjectRead, ReportStatus } from '../../../core/models';
import { NotificationService } from '../../../core/services/notification.service';
import { PhotoService } from '../../../core/services/photo.service';
import { ProjectService } from '../../../core/services/project.service';
import { ReportsService } from '../../../core/services/reports.service';
import { formatHttpError } from '../../../core/services/error-format';
import { PhotoAnnotatorComponent } from '../../../shared/components/photo-annotator/photo-annotator.component';
import { todayIso } from '../../../shared/utils/format';

interface DraftPhoto {
  id: string;
  file: Blob;
  filename: string;
  previewUrl: string;
  caption: string;
  annotating: boolean;
}

let draftPhotoCounter = 0;

const TOTAL_STEPS = 4;

@Component({
  selector: 'app-daily-report-form',
  imports: [CommonModule, FormsModule, RouterLink, PhotoAnnotatorComponent],
  templateUrl: './daily-report-form.component.html',
  styleUrl: './daily-report-form.component.scss',
})
export class DailyReportFormComponent implements OnInit {
  private readonly reports = inject(ReportsService);
  private readonly projects = inject(ProjectService);
  private readonly photos = inject(PhotoService);
  private readonly notifications = inject(NotificationService);
  private readonly router = inject(Router);

  @Input() slug!: string;

  protected readonly project = signal<ProjectRead | null>(null);
  // Explizites Signal für die Sections — sicherer als `project()?.sections`
  // im Template (Angular-Change-Detection greift garantiert).
  protected readonly sections = computed(() => this.project()?.sections ?? []);
  protected readonly submitting = signal(false);
  protected readonly draftPhotos = signal<DraftPhoto[]>([]);
  protected readonly photoCount = computed(() => this.draftPhotos().length);

  protected readonly totalSteps = TOTAL_STEPS;
  protected readonly currentStep = signal<number>(1);
  protected readonly progressPercent = computed(
    () => (this.currentStep() / this.totalSteps) * 100,
  );

  protected form: DailyReportForm = this.defaultForm();

  protected readonly canGoNext = computed<boolean>(() => {
    const step = this.currentStep();
    if (step === 1) {
      return !!this.form.report_date;
    }
    if (step === 2) {
      return this.form.team.trim().length > 0;
    }
    if (step === 3) {
      return (
        this.form.completed_work.trim().length > 0
        && this.form.open_work.trim().length > 0
      );
    }
    return true;
  });

  ngOnInit(): void {
    this.restoreDraft();
    this.projects.get(this.slug).subscribe({
      next: (project) => {
        this.project.set(project);
        if (project.sections.length > 0 && this.form.section_number === null) {
          this.form.section_number = project.sections[0].number;
        }
      },
      error: (response) =>
        this.notifications.showError(
          formatHttpError(response, 'Projekt konnte nicht geladen werden.'),
        ),
    });
  }

  protected setStatus(status: ReportStatus): void {
    this.form.status = status;
    this.persistDraft();
  }

  protected nextStep(): void {
    if (!this.canGoNext()) {
      return;
    }
    this.persistDraft();
    this.currentStep.update((step) => Math.min(this.totalSteps, step + 1));
  }

  protected prevStep(): void {
    this.currentStep.update((step) => Math.max(1, step - 1));
  }

  protected goToStep(step: number): void {
    if (step < 1 || step > this.totalSteps) return;
    this.currentStep.set(step);
  }

  protected persistDraft(): void {
    if (typeof localStorage === 'undefined') return;
    try {
      localStorage.setItem(this.draftKey(), JSON.stringify({
        form: this.form,
        step: this.currentStep(),
      }));
    } catch {
      /* Quota überschritten o.ä. — Draft ist nice-to-have, kein Hard-Fail. */
    }
  }

  private restoreDraft(): void {
    if (typeof localStorage === 'undefined') return;
    try {
      const raw = localStorage.getItem(this.draftKey());
      if (!raw) return;
      const parsed = JSON.parse(raw) as { form?: DailyReportForm; step?: number };
      if (parsed.form) {
        this.form = { ...this.defaultForm(), ...parsed.form };
      }
      if (parsed.step && parsed.step >= 1 && parsed.step <= this.totalSteps) {
        this.currentStep.set(parsed.step);
      }
    } catch {
      /* Korrupter Draft → ignorieren. */
    }
  }

  private clearDraft(): void {
    if (typeof localStorage === 'undefined') return;
    try {
      localStorage.removeItem(this.draftKey());
    } catch {
      /* ignore */
    }
  }

  private draftKey(): string {
    return `daily-report-draft:${this.slug}`;
  }

  protected onPhotoFilesSelected(event: Event): void {
    const target = event.target as HTMLInputElement;
    if (!target.files || target.files.length === 0) {
      return;
    }
    const additions: DraftPhoto[] = [];
    for (let i = 0; i < target.files.length; i += 1) {
      const file = target.files.item(i);
      if (!file) {
        continue;
      }
      additions.push({
        id: `draft-${++draftPhotoCounter}`,
        file,
        filename: file.name,
        previewUrl: URL.createObjectURL(file),
        caption: '',
        annotating: false,
      });
    }
    this.draftPhotos.update((current) => [...current, ...additions]);
    target.value = '';
  }

  protected removePhoto(id: string): void {
    this.draftPhotos.update((current) => {
      const remaining: DraftPhoto[] = [];
      for (const photo of current) {
        if (photo.id === id) {
          URL.revokeObjectURL(photo.previewUrl);
          continue;
        }
        remaining.push(photo);
      }
      return remaining;
    });
  }

  protected updateCaption(id: string, caption: string): void {
    this.draftPhotos.update((current) =>
      current.map((photo) =>
        photo.id === id ? { ...photo, caption } : photo,
      ),
    );
  }

  protected toggleAnnotator(id: string): void {
    this.draftPhotos.update((current) =>
      current.map((photo) =>
        photo.id === id
          ? { ...photo, annotating: !photo.annotating }
          : { ...photo, annotating: false },
      ),
    );
  }

  protected onAnnotationSaved(id: string, blob: Blob): void {
    this.draftPhotos.update((current) =>
      current.map((photo) => {
        if (photo.id !== id) {
          return photo;
        }
        URL.revokeObjectURL(photo.previewUrl);
        const annotatedFilename = photo.filename.replace(/\.[^.]+$/, '') + '.annotated.png';
        return {
          ...photo,
          file: blob,
          filename: annotatedFilename,
          previewUrl: URL.createObjectURL(blob),
          annotating: false,
        };
      }),
    );
  }

  protected cancelAnnotation(id: string): void {
    this.draftPhotos.update((current) =>
      current.map((photo) =>
        photo.id === id ? { ...photo, annotating: false } : photo,
      ),
    );
  }

  protected submit(): void {
    if (this.submitting()) {
      return;
    }
    this.notifications.clear();
    this.submitting.set(true);

    const drafts = this.draftPhotos();

    this.reports
      .submitDailyReport(this.slug, this.form)
      .pipe(
        switchMap((report) => {
          if (drafts.length === 0) {
            return of(report);
          }
          const uploads = drafts.map((draft) => {
            const file =
              draft.file instanceof File
                ? draft.file
                : new File([draft.file], draft.filename, { type: 'image/png' });
            return this.photos
              .upload(this.slug, file, {
                sectionNumber: this.form.section_number,
                dailyReportId: report.id,
                caption: draft.caption || null,
              })
              .pipe(catchError(() => of(null)));
          });
          return forkJoin(uploads).pipe(switchMap(() => of(report)));
        }),
      )
      .subscribe({
        next: () => {
          this.submitting.set(false);
          for (const draft of drafts) {
            URL.revokeObjectURL(draft.previewUrl);
          }
          this.draftPhotos.set([]);
          this.clearDraft();
          this.notifications.showMessage('Tagesbericht gespeichert.');
          this.reports.loadDailyReports(this.slug).subscribe({ error: () => undefined });
          this.reports.loadSummary(this.slug).subscribe({ error: () => undefined });
          this.router.navigate(['/projects', this.slug, 'reports', 'daily']);
        },
        error: (response) => {
          this.submitting.set(false);
          this.notifications.showError(
            formatHttpError(response, 'Tagesbericht konnte nicht gespeichert werden.'),
          );
        },
      });
  }

  private defaultForm(): DailyReportForm {
    return {
      section_number: null,
      report_date: todayIso(),
      status: 'green',
      team: '',
      completed_work: '',
      open_work: '',
      material_missing: '',
      blockers: '',
      notes: '',
    };
  }
}
