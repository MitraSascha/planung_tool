import { CommonModule } from '@angular/common';
import { Component, Input, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { forkJoin, of, Observable } from 'rxjs';
import { catchError, switchMap } from 'rxjs/operators';

import { DailyReportForm, DailyReportRead, MaterialItem, ProjectMemberRead, ProjectRead, ReportStatus } from '../../../core/models';
import { AuthService } from '../../../core/services/auth.service';
import { MaterialService } from '../../../core/services/material.service';
import { NotificationService } from '../../../core/services/notification.service';
import { PhotoService } from '../../../core/services/photo.service';
import { ProjectService } from '../../../core/services/project.service';
import { ReportsService } from '../../../core/services/reports.service';
import { formatHttpError } from '../../../core/services/error-format';
import { MaterialPickerComponent } from '../../../shared/components/material-picker/material-picker.component';
import { MaterialCatalogPickerComponent } from '../../../shared/components/material-catalog-picker/material-catalog-picker.component';
import { PhotoAnnotatorComponent } from '../../../shared/components/photo-annotator/photo-annotator.component';
import {
  PttButtonComponent,
  PttTranscriptionEvent,
} from '../../../shared/components/ptt-button/ptt-button.component';
import { MaterialCatalogEntry } from '../../../core/services/material-catalog.service';
import { todayIso } from '../../../shared/utils/format';

interface DraftUsage {
  id: string;
  material_item_id: number;
  material_name: string;
  unit: string | null;
  qty_used: number;
  notes: string;
}
let draftUsageCounter = 0;

/** Materialerfassung (Issue #2): pro Auswahl aus dem Katalog + Mengenangabe
 *  wird beim Submit eine eigene MaterialIssue erzeugt. */
interface DraftMaterialIssue {
  id: string;
  catalog_id: number;
  artikelnummer: string;
  name: string;
  qty: number;
  note: string;
}
let draftMaterialIssueCounter = 0;

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
/** Bump bei jeder Step-Struktur-Änderung — alte Drafts werden dann remapped. */
const DRAFT_VERSION = 2;

@Component({
  selector: 'app-daily-report-form',
  imports: [
    CommonModule,
    FormsModule,
    RouterLink,
    PhotoAnnotatorComponent,
    MaterialPickerComponent,
    MaterialCatalogPickerComponent,
    PttButtonComponent,
  ],
  templateUrl: './daily-report-form.component.html',
  styleUrl: './daily-report-form.component.scss',
})
export class DailyReportFormComponent implements OnInit {
  private readonly reports = inject(ReportsService);
  private readonly projects = inject(ProjectService);
  private readonly photos = inject(PhotoService);
  private readonly materials = inject(MaterialService);
  private readonly notifications = inject(NotificationService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  @Input() slug!: string;
  /** Wenn gesetzt: Edit-Modus — Form wird mit dem bestehenden Bericht vorbelegt
   *  und der Submit ruft PATCH statt POST. Route-Param via withComponentInputBinding. */
  @Input() reportId?: string | number;

  protected readonly editingReport = signal<DailyReportRead | null>(null);
  protected readonly isEditing = computed(() => this.editingReport() != null);

  protected readonly project = signal<ProjectRead | null>(null);
  // Explizites Signal für die Sections — sicherer als `project()?.sections`
  // im Template (Angular-Change-Detection greift garantiert).
  protected readonly sections = computed(() => this.project()?.sections ?? []);
  protected readonly submitting = signal(false);
  /**
   * Wenn ein vorheriger Submit den Daily-Report bereits erfolgreich angelegt
   * hat aber die Anhänge (Photos/Usages) fehlgeschlagen sind, merken wir uns
   * die report.id hier. Beim nächsten "Speichern" wird KEIN neuer Report mehr
   * angelegt — nur die noch fehlenden Anhänge mit dieser ID nachgereicht.
   * Damit entstehen keine Duplikat-Reports bei Retry.
   */
  private savedReportId: number | null = null;
  protected readonly draftPhotos = signal<DraftPhoto[]>([]);
  protected readonly photoCount = computed(() => this.draftPhotos().length);

  // Material-Verbrauchsbuchungen für diesen Bericht
  protected readonly materialItems = signal<MaterialItem[]>([]);
  protected readonly draftUsages = signal<DraftUsage[]>([]);
  protected usageDraft = { material_item_id: null as number | null, qty_used: null as number | null, notes: '' };

  // Materialerfassung (Picklist aus dem Katalog): jeder Draft wird beim Submit
  // zu einer eigenen MaterialIssue gemacht. Freitext-Feld `material_missing`
  // bleibt parallel für „nicht in Liste"-Fälle.
  protected readonly draftMaterialIssues = signal<DraftMaterialIssue[]>([]);

  // Material-Auswahl (Filter, Gruppierung, Anzeige) liegt jetzt vollständig
  // im <app-material-picker> — eigene Bottom-Sheet-Komponente mit Suche,
  // 2-zeiligen Items und Group-Headern. Sie respektiert
  // `currentSection`-Input und blendet Items anderer Abschnitte aus.

  // Team-Multi-Select: Projekt-Mitglieder
  protected readonly members = signal<ProjectMemberRead[]>([]);

  protected readonly totalSteps = TOTAL_STEPS;
  protected readonly currentStep = signal<number>(1);
  protected readonly progressPercent = computed(
    () => (this.currentStep() / this.totalSteps) * 100,
  );

  protected form: DailyReportForm = this.defaultForm();

  /**
   * Plain method statt computed-Signal: `this.form` ist ein Plain Object,
   * ngModel-Updates triggern keine Signal-Notifikation. Methode wird bei
   * jedem Change-Detection-Cycle neu evaluiert (= bei jedem Tastendruck
   * via ngModel-Binding).
   */
  protected canGoNext(): boolean {
    const step = this.currentStep();
    if (step === 1) {
      // Wann & Wer: Datum pflicht + mindestens eine Team-Quelle
      return (
        !!this.form.report_date
        && (this.form.team.trim().length > 0 || this.form.attendee_user_ids.length > 0)
      );
    }
    if (step === 2) {
      // Neuer Flow: ein Roh-Feld „Arbeitstagerfassung" reicht. Backend splittet
      // beim Speichern. Falls der User dennoch direkt completed/open getippt
      // hat (z.B. Edit-Modus eines Berichts ohne raw_work_log), akzeptieren wir
      // auch das als gültig.
      const raw = (this.form.raw_work_log || '').trim();
      const completed = this.form.completed_work.trim();
      const open = this.form.open_work.trim();
      return raw.length > 0 || completed.length > 0 || open.length > 0;
    }
    return true;
  }

  ngOnInit(): void {
    const editId = this.reportIdAsNumber();
    if (editId != null) {
      this.loadReportForEdit(editId);
    } else {
      this.restoreDraft();
      // Ersteller automatisch als anwesend vorbelegen (Frage 1, 2026-05-19).
      // Nur wenn der Wizard frisch startet — bei einem restoreten Draft hat
      // der User schon selbst gewählt, das respektieren wir.
      this.preselectCurrentUserAsAttendee();
    }
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
    this.reloadMaterialItems();
    this.reports.loadMembers(this.slug).subscribe({
      next: (rows) => {
        this.members.set(rows);
        // Members-Liste kommt async — Pre-Select erst hier nochmal versuchen,
        // falls der User vorher nicht im Roster gefunden wurde.
        this.preselectCurrentUserAsAttendee();
      },
      error: () => {
        // Falls keine Mitglieder zugeordnet — Multi-Select bleibt leer, Freitext bleibt nutzbar.
      },
    });
  }

  /** Setzt den eingeloggten User als attendee, falls er Projekt-Mitglied ist
   *  und noch nicht in der Liste steht. Im Edit-Modus passiert nichts —
   *  dort gilt was im Bericht steht. */
  private preselectCurrentUserAsAttendee(): void {
    if (this.isEditing()) return;
    const me = this.auth.currentUser();
    if (!me) return;
    // Wenn die Members-Liste bereits geladen ist, prüfen wir Mitgliedschaft.
    // Sonst legen wir erstmal trotzdem rein (Backend lehnt Nicht-Member eh ab).
    const members = this.members();
    const isMember = members.length === 0 || members.some((m) => m.user_id === me.id);
    if (!isMember) return;
    if (!this.form.attendee_user_ids.includes(me.id)) {
      this.form.attendee_user_ids = [...this.form.attendee_user_ids, me.id];
      this.persistDraft();
    }
  }

  /** Material-Stamm vom Server neu laden — nach Anlegen eines Artikelstamm-
   *  Posten muss der Picker den neuen Eintrag sehen. */
  protected reloadMaterialItems(): void {
    this.materials.listItems(this.slug).subscribe({
      next: (items) => this.materialItems.set(items),
      error: () => {
        // Optional — bei leerem Material-Stamm bleibt der Picker leer.
      },
    });
  }

  private reportIdAsNumber(): number | null {
    if (this.reportId == null || this.reportId === '') return null;
    const n = Number(this.reportId);
    return Number.isFinite(n) ? n : null;
  }

  /** Lade die Liste der Tagesberichte, finde den zu editierenden, vorbelege
   *  die Form. Wir nutzen die Listen-Route, weil es keinen GET-by-id-Endpoint
   *  gibt — der Backend filtert eh schon auf den User bei Rolle Monteur. */
  private loadReportForEdit(reportId: number): void {
    this.reports.loadDailyReports(this.slug).subscribe({
      next: (reports) => {
        const target = reports.find((r) => r.id === reportId);
        if (!target) {
          this.notifications.showError('Tagesbericht nicht gefunden.');
          this.router.navigate(['/projects', this.slug, 'reports']);
          return;
        }
        if (!target.editable) {
          this.notifications.showError(
            'Dieser Tagesbericht kann nicht mehr bearbeitet werden (Bearbeitungs-Fenster abgelaufen).',
          );
          this.router.navigate(['/projects', this.slug, 'reports']);
          return;
        }
        this.editingReport.set(target);
        this.form = {
          section_number: target.section_number ?? null,
          report_date: target.report_date,
          status: target.status,
          team: target.team ?? '',
          attendee_user_ids: target.attendee_user_ids ?? [],
          raw_work_log: target.raw_work_log ?? '',
          raw_work_log_language: target.raw_work_log_language ?? null,
          completed_work: target.completed_work ?? '',
          open_work: target.open_work ?? '',
          material_missing: target.material_missing ?? '',
          blockers: target.blockers ?? '',
          notes: target.notes ?? '',
          ist_hours: target.ist_hours ?? null,
          safety_psa: target.safety_psa ?? null,
          safety_tools: target.safety_tools ?? null,
          safety_material: target.safety_material ?? null,
          safety_workarea: target.safety_workarea ?? null,
          safety_approval: target.safety_approval ?? null,
        };
        // Im Edit-Modus startet der Wizard auf Schritt 2 (Inhalte), weil
        // Datum/Team meist nicht das ist, was korrigiert werden muss.
        this.currentStep.set(2);
      },
      error: (response) =>
        this.notifications.showError(
          formatHttpError(response, 'Bericht konnte nicht geladen werden.'),
        ),
    });
  }

  protected toggleAttendee(userId: number): void {
    const current = new Set(this.form.attendee_user_ids);
    if (current.has(userId)) current.delete(userId);
    else current.add(userId);
    this.form.attendee_user_ids = [...current];
    this.persistDraft();
  }

  protected isAttendeeSelected(userId: number): boolean {
    return this.form.attendee_user_ids.includes(userId);
  }

  protected addUsageDraft(): void {
    const itemId = this.usageDraft.material_item_id;
    const qty = this.usageDraft.qty_used;
    if (itemId == null || qty == null || qty <= 0) {
      return;
    }
    const item = this.materialItems().find((m) => m.id === itemId);
    if (!item) return;
    const entry: DraftUsage = {
      id: `usage-${++draftUsageCounter}`,
      material_item_id: itemId,
      material_name: item.name,
      unit: item.unit,
      qty_used: qty,
      notes: this.usageDraft.notes,
    };
    this.draftUsages.update((current) => [...current, entry]);
    this.usageDraft = { material_item_id: null, qty_used: null, notes: '' };
  }

  protected removeUsageDraft(id: string): void {
    this.draftUsages.update((current) => current.filter((u) => u.id !== id));
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
        version: DRAFT_VERSION,
        form: this.form,
        step: this.currentStep(),
      }));
    } catch {
      /* Quota überschritten o.ä. — Draft ist nice-to-have, kein Hard-Fail. */
    }
  }

  /**
   * Mappt einen Step aus einem alten 5-Schritt-Wizard auf das aktuelle
   * 4-Schritt-Layout: Wann(1) + Wer(2) → Wann&Wer(1); Was(3)→2; Material(4)→3;
   * Senden(5)→4. Drafts ohne Versionsfeld werden als „alt" behandelt.
   */
  private remapLegacyStep(step: number): number {
    const map: Record<number, number> = { 1: 1, 2: 1, 3: 2, 4: 3, 5: 4 };
    return map[step] ?? 1;
  }

  private restoreDraft(): void {
    if (typeof localStorage === 'undefined') return;
    try {
      const raw = localStorage.getItem(this.draftKey());
      if (!raw) return;
      const parsed = JSON.parse(raw) as { version?: number; form?: DailyReportForm; step?: number };
      if (parsed.form) {
        this.form = { ...this.defaultForm(), ...parsed.form };
      }
      if (parsed.step && parsed.step >= 1) {
        const step = parsed.version === DRAFT_VERSION
          ? parsed.step
          : this.remapLegacyStep(parsed.step);
        if (step >= 1 && step <= this.totalSteps) {
          this.currentStep.set(step);
        }
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
    const usageDrafts = this.draftUsages();
    const materialDrafts = this.draftMaterialIssues();

    // Drei Pfade:
    //  1. Edit-Modus  → PATCH auf den existierenden Bericht.
    //  2. Retry-Pfad  → Bericht ist bereits angelegt, nur Anhänge erneut versuchen.
    //  3. Neu-Anlage  → POST.
    const editing = this.editingReport();
    const reportStream$ = editing
      ? this.reports.updateDailyReport(this.slug, editing.id, this.form)
      : this.savedReportId != null
        ? of({ id: this.savedReportId } as DailyReportRead)
        : this.reports.submitDailyReport(this.slug, this.form);

    reportStream$
      .pipe(
        switchMap((report) => {
          // Sobald der Report angelegt ist (oder schon vorher war), merken
          // für Retry-Pfad — bei Anhang-Fehlern reuse statt neu anlegen.
          this.savedReportId = report.id;
          const tasks: Observable<{ kind: 'photo' | 'usage' | 'material'; draftId: string; ok: boolean; error?: unknown }>[] = [];
          for (const draft of drafts) {
            const file =
              draft.file instanceof File
                ? draft.file
                : new File([draft.file], draft.filename, { type: 'image/png' });
            tasks.push(
              this.photos
                .upload(this.slug, file, {
                  sectionNumber: this.form.section_number,
                  dailyReportId: report.id,
                  caption: draft.caption || null,
                })
                .pipe(
                  // Erfolgreich → ok:true
                  switchMap(() => of({ kind: 'photo' as const, draftId: draft.id, ok: true })),
                  catchError((err) => of({ kind: 'photo' as const, draftId: draft.id, ok: false, error: err })),
                ),
            );
          }
          for (const u of usageDrafts) {
            tasks.push(
              this.materials
                .createUsage(this.slug, {
                  material_item_id: u.material_item_id,
                  daily_report_id: report.id,
                  section_number: this.form.section_number,
                  qty_used: u.qty_used,
                  unit: u.unit,
                  used_at: this.form.report_date,
                  notes: u.notes || null,
                })
                .pipe(
                  switchMap(() => of({ kind: 'usage' as const, draftId: u.id, ok: true })),
                  catchError((err) => of({ kind: 'usage' as const, draftId: u.id, ok: false, error: err })),
                ),
            );
          }
          // Materialerfassung-Drafts: pro Auswahl eine MaterialIssue posten.
          // Format der Beschreibung: "<qty>× <artnr> — <name>" (+ Notiz wenn
          // gesetzt). Backend triggert Push an Lead-Rollen.
          for (const m of materialDrafts) {
            const descParts = [`${m.qty}× ${m.artikelnummer} — ${m.name}`];
            if (m.note.trim()) descParts.push(m.note.trim());
            tasks.push(
              this.reports
                .createMaterialIssue(this.slug, {
                  section_number: this.form.section_number,
                  description: descParts.join(' · '),
                  priority: 'normal',
                })
                .pipe(
                  switchMap(() => of({ kind: 'material' as const, draftId: m.id, ok: true })),
                  catchError((err) => of({ kind: 'material' as const, draftId: m.id, ok: false, error: err })),
                ),
            );
          }
          if (tasks.length === 0) {
            return of({ report, results: [] as Array<{ kind: 'photo' | 'usage' | 'material'; draftId: string; ok: boolean; error?: unknown }> });
          }
          return forkJoin(tasks).pipe(switchMap((results) => of({ report, results })));
        }),
      )
      .subscribe({
        next: ({ results }) => {
          this.submitting.set(false);
          const failedPhotoIds = new Set(results.filter((r) => r.kind === 'photo' && !r.ok).map((r) => r.draftId));
          const failedUsageIds = new Set(results.filter((r) => r.kind === 'usage' && !r.ok).map((r) => r.draftId));
          const failedMaterialIds = new Set(results.filter((r) => r.kind === 'material' && !r.ok).map((r) => r.draftId));

          // Erfolgreiche Photos: URL freigeben + entfernen. Failed behalten.
          for (const draft of drafts) {
            if (!failedPhotoIds.has(draft.id)) {
              URL.revokeObjectURL(draft.previewUrl);
            }
          }
          this.draftPhotos.update((current) => current.filter((p) => failedPhotoIds.has(p.id)));
          this.draftUsages.update((current) => current.filter((u) => failedUsageIds.has(u.id)));
          this.draftMaterialIssues.update((current) => current.filter((m) => failedMaterialIds.has(m.id)));
          this.clearDraft();

          const failedCount = failedPhotoIds.size + failedUsageIds.size + failedMaterialIds.size;
          if (failedCount > 0) {
            // Bericht ist gespeichert, aber Anhänge teilweise nicht — KRITISCH
            // dass der User das sieht, da er sich auf den Material-Verbau verlässt.
            const parts: string[] = [];
            if (failedUsageIds.size > 0) parts.push(`${failedUsageIds.size} Verbrauchsbuchung(en)`);
            if (failedMaterialIds.size > 0) parts.push(`${failedMaterialIds.size} Materialmeldung(en)`);
            if (failedPhotoIds.size > 0) parts.push(`${failedPhotoIds.size} Foto(s)`);
            this.notifications.showError(
              `Tagesbericht gespeichert, aber ${parts.join(' und ')} konnten nicht hochgeladen werden. ` +
              `Die Drafts bleiben im Formular — bitte erneut speichern.`,
            );
            this.reports.loadDailyReports(this.slug).subscribe({ error: () => undefined });
            this.reports.loadSummary(this.slug).subscribe({ error: () => undefined });
            // Nicht navigieren — User muss erneut speichern
            return;
          }

          // Alles durch — Retry-State zurücksetzen, sonst würde der nächste
          // Submit am gleichen ID kleben.
          this.savedReportId = null;
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
      attendee_user_ids: [],
      raw_work_log: '',
      raw_work_log_language: null,
      completed_work: '',
      open_work: '',
      material_missing: '',
      blockers: '',
      notes: '',
    };
  }

  /** Push-to-Talk-Output ins Roh-Feld einfügen. Vorhandenen Text behalten —
   *  Voice-Diktate sind meist ergänzend, nicht ersetzend. */
  protected onPttArbeitstag(event: PttTranscriptionEvent): void {
    const existing = (this.form.raw_work_log || '').trim();
    const incoming = event.text.trim();
    this.form.raw_work_log = existing
      ? `${existing}\n${incoming}`
      : incoming;
    if (event.source === 'server' && event.language) {
      this.form.raw_work_log_language = event.language;
    }
    this.persistDraft();
  }

  /** Push-to-Talk für ein beliebiges Freitextfeld: appended ans Ende. */
  protected appendPttToField(
    fieldKey: 'material_missing' | 'blockers' | 'notes',
    event: PttTranscriptionEvent,
  ): void {
    const existing = (this.form[fieldKey] || '').trim();
    const incoming = event.text.trim();
    this.form[fieldKey] = existing ? `${existing}\n${incoming}` : incoming;
    this.persistDraft();
  }

  // ─── Materialerfassung (Picklist aus dem Katalog) ────────────────────────

  /** Vom Picker ausgewählten Artikel als neuen Draft anlegen (Default-Menge 1). */
  protected onCatalogPicked(entry: MaterialCatalogEntry): void {
    const draft: DraftMaterialIssue = {
      id: `mat-${++draftMaterialIssueCounter}`,
      catalog_id: entry.id,
      artikelnummer: entry.artikelnummer,
      name: entry.beschreibung_2
        ? `${entry.beschreibung_1} — ${entry.beschreibung_2}`
        : entry.beschreibung_1,
      qty: 1,
      note: '',
    };
    this.draftMaterialIssues.update((list) => [...list, draft]);
  }

  protected updateMaterialDraftQty(id: string, qty: number): void {
    this.draftMaterialIssues.update((list) =>
      list.map((d) => (d.id === id ? { ...d, qty: Math.max(0, qty) } : d)),
    );
  }

  protected updateMaterialDraftNote(id: string, note: string): void {
    this.draftMaterialIssues.update((list) =>
      list.map((d) => (d.id === id ? { ...d, note } : d)),
    );
  }

  protected removeMaterialDraft(id: string): void {
    this.draftMaterialIssues.update((list) => list.filter((d) => d.id !== id));
  }
}
