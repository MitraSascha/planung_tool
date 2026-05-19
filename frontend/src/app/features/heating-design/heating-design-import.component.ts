import { CommonModule } from '@angular/common';
import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import {
  CIRCUIT_FIELD_LABELS,
  ExternalSourceMapping,
  HeatingCircuitPreview,
  HeatingDesignImportPreview,
  HeatingImporterInfo,
  KNOWN_CIRCUIT_FIELDS,
  SECONDARY_CIRCUIT_FIELDS,
} from '../../core/models';
import { HeatingService } from '../../core/services/heating.service';
import { NotificationService } from '../../core/services/notification.service';
import { formatHttpError } from '../../core/services/error-format';

type WizardStep = 'select' | 'preview';

@Component({
  selector: 'app-heating-design-import',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './heating-design-import.component.html',
  styleUrl: './heating-design-import.component.scss',
})
export class HeatingDesignImportComponent implements OnInit {
  private readonly heating = inject(HeatingService);
  private readonly notifications = inject(NotificationService);
  private readonly router = inject(Router);

  @Input() slug!: string;

  protected readonly knownFields = KNOWN_CIRCUIT_FIELDS;
  protected readonly fieldLabels = CIRCUIT_FIELD_LABELS;

  protected readonly step = signal<WizardStep>('select');
  protected readonly busy = signal(false);

  protected readonly importers = signal<HeatingImporterInfo[]>([]);
  protected readonly mappings = signal<ExternalSourceMapping[]>([]);
  protected readonly preview = signal<HeatingDesignImportPreview | null>(null);
  protected readonly previewSourceFile = signal<string>('');

  // Selection step state
  protected selectedFile: File | null = null;
  protected selectedFileName = '';
  protected adapterHint = '';
  protected mappingName = '';

  // Preview step state — column mapping that the user is editing.
  // Key = canonical field name; value = source column name (or empty string for "not mapped").
  protected mappingState: Record<string, string> = {};
  protected sourceColumns: string[] = [];
  /**
   * Grouped columns for the manual-mapping dropdown when the file has
   * multiple sheets. Empty when the file is single-sheet — in that case the
   * UI falls back to the flat ``sourceColumns`` list.
   * Shape: [{ sheet: 'Daten', columns: [{ header, label }, …] }, …]
   */
  protected sourceColumnGroups: Array<{
    sheet: string;
    columns: Array<{ header: string; label: string }>;
  }> = [];

  // Save-mapping modal state
  protected showSaveMappingModal = false;
  protected saveMappingName = '';
  protected saveMappingDescription = '';

  ngOnInit(): void {
    this.heating.listImporters().subscribe({
      next: (list) => this.importers.set(list),
      error: () => undefined,
    });
    this.heating.listMappings().subscribe({
      next: (list) => this.mappings.set(list),
      error: () => undefined,
    });
  }

  // -----------------------------------------------------------------
  // Step 1 — File selection
  // -----------------------------------------------------------------

  protected onFileChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files && input.files.length > 0 ? input.files[0] : null;
    this.selectedFile = file;
    this.selectedFileName = file ? file.name : '';
  }

  protected canRequestPreview(): boolean {
    return !!this.selectedFile && !this.busy();
  }

  protected requestPreview(): void {
    if (!this.selectedFile) {
      this.notifications.showError('Bitte zuerst eine Datei wählen.');
      return;
    }
    const mappingJson = this.buildMappingJsonForReapply();
    this.busy.set(true);
    this.notifications.clear();
    this.heating
      .importPreview(
        this.slug,
        this.selectedFile,
        this.adapterHint || null,
        this.mappingName || null,
        mappingJson,
      )
      .subscribe({
        next: (preview) => {
          this.applyPreview(preview);
          this.step.set('preview');
          this.busy.set(false);
        },
        error: (response) => {
          this.busy.set(false);
          this.notifications.showError(
            formatHttpError(response, 'Vorschau konnte nicht erzeugt werden.'),
          );
        },
      });
  }

  private buildMappingJsonForReapply(): string | null {
    // First call uses adapter auto-detect or named mapping. Only build a JSON
    // payload when the user has actively edited the mapping in the preview step.
    if (this.step() !== 'preview') {
      return null;
    }
    const circuit_columns: Record<string, string> = {};
    for (const field of this.knownFields) {
      const src = this.mappingState[field];
      if (src && src.trim().length > 0) {
        circuit_columns[field] = src;
      }
    }
    return JSON.stringify({ circuit_columns, design_overrides: {} });
  }

  // -----------------------------------------------------------------
  // Step 2 — Preview / Mapping
  // -----------------------------------------------------------------

  private applyPreview(preview: HeatingDesignImportPreview): void {
    this.preview.set(preview);
    this.previewSourceFile.set(preview.source_file);
    const next: Record<string, string> = {};
    for (const field of this.knownFields) {
      next[field] = preview.detected_columns?.[field] ?? '';
    }
    this.mappingState = next;
    // Source-columns universe = ALL headers seen in the file (from
    // source_columns), not just the auto-detected ones. This lets the user
    // pick from every original column in the manual-mapping dropdown.
    const headers = Object.keys(preview.source_columns ?? {});
    if (headers.length === 0) {
      // Fallback for older backends that don't return source_columns.
      const set = new Set<string>();
      for (const value of Object.values(preview.detected_columns ?? {})) {
        if (value) set.add(value);
      }
      this.sourceColumns = Array.from(set).sort((a, b) => a.localeCompare(b, 'de'));
    } else {
      this.sourceColumns = headers.sort((a, b) => a.localeCompare(b, 'de'));
    }

    // Build per-sheet groups for the manual-mapping dropdown if the backend
    // delivered the multi-sheet column index. We fold in the merged
    // ``source_columns`` headers as well so that every selectable value in
    // the merged universe also appears in the grouped view.
    this.sourceColumnGroups = this.buildSourceColumnGroups(preview);
  }

  private buildSourceColumnGroups(
    preview: HeatingDesignImportPreview,
  ): Array<{ sheet: string; columns: Array<{ header: string; label: string }> }> {
    const bySheet = preview.source_columns_by_sheet;
    if (!bySheet || Object.keys(bySheet).length === 0) {
      return [];
    }
    const groups: Array<{
      sheet: string;
      columns: Array<{ header: string; label: string }>;
    }> = [];
    for (const sheetName of Object.keys(bySheet)) {
      const cols = bySheet[sheetName] ?? {};
      const entries: Array<{ header: string; label: string }> = [];
      for (const header of Object.keys(cols).sort((a, b) =>
        a.localeCompare(b, 'de'),
      )) {
        const samples = cols[header] ?? [];
        const shown = samples.slice(0, 3).join(', ');
        const more = samples.length > 3 ? ', …' : '';
        const label = samples.length > 0
          ? `${header} — z.B. ${shown}${more}`
          : header;
        entries.push({ header, label });
      }
      if (entries.length > 0) {
        groups.push({ sheet: sheetName, columns: entries });
      }
    }
    return groups;
  }

  /** Compact one-line label for the mapping dropdown: "WE (Wohnung 1, Wohnung 2, …)". */
  protected sourceColumnLabel(header: string): string {
    const samples = this.preview()?.source_columns?.[header] ?? [];
    if (samples.length === 0) {
      return header;
    }
    const shown = samples.slice(0, 3).join(', ');
    const more = samples.length > 3 ? ', …' : '';
    return `${header} — z.B. ${shown}${more}`;
  }

  protected isFieldInFile(field: string): boolean {
    return !!this.mappingState[field];
  }

  protected showManualMapping = false;
  protected toggleManualMapping(): void {
    this.showManualMapping = !this.showManualMapping;
  }

  protected detectedFieldsCount(): number {
    return Object.values(this.mappingState).filter((v) => !!v).length;
  }

  /**
   * Primary fields: only the ones that actually appear in real heating-load
   * sheets ("Daten"-style Aggregate). Strand is special — comes from the
   * Sheet names, not from any column, so it's not mappable manually.
   *
   * Primary order: room, floor, area_sqm, heat_load_w, volume_flow_lph.
   * Strand is shown in the auto-overview but NOT in the manual table.
   */
  private readonly _primaryFieldOrder = [
    'room',
    'floor',
    'area_sqm',
    'heat_load_w',
    'volume_flow_lph',
  ] as const;

  protected primaryFields(): string[] {
    return [...this._primaryFieldOrder];
  }

  protected secondaryFields(): string[] {
    return this.knownFields.filter(
      (f) =>
        f !== 'strand'
        && !this._primaryFieldOrder.includes(f as any),
    );
  }

  /** Strand is auto-extracted from Sheet names ('Strang 1', …) — not manually mappable. */
  protected strandAutoCount(): number {
    const circuits = this.preview()?.circuits ?? [];
    return circuits.filter((c) => !!c.strand).length;
  }

  protected showSecondaryFields = false;
  protected toggleSecondaryFields(): void {
    this.showSecondaryFields = !this.showSecondaryFields;
  }

  protected setMappingValue(field: string, value: string): void {
    this.mappingState = { ...this.mappingState, [field]: value };
  }

  protected reapplyMapping(): void {
    if (!this.selectedFile) {
      this.notifications.showError(
        'Originaldatei nicht mehr verfügbar — bitte erneut hochladen.',
      );
      this.step.set('select');
      return;
    }
    const circuit_columns: Record<string, string> = {};
    for (const field of this.knownFields) {
      const src = this.mappingState[field];
      if (src && src.trim().length > 0) {
        circuit_columns[field] = src;
      }
    }
    const mappingJson = JSON.stringify({
      circuit_columns,
      design_overrides: {},
    });
    this.busy.set(true);
    this.notifications.clear();
    this.heating
      .importPreview(
        this.slug,
        this.selectedFile,
        this.adapterHint || null,
        null,
        mappingJson,
      )
      .subscribe({
        next: (preview) => {
          this.applyPreview(preview);
          this.busy.set(false);
          this.notifications.showMessage('Mapping neu angewendet.');
        },
        error: (response) => {
          this.busy.set(false);
          this.notifications.showError(
            formatHttpError(response, 'Mapping konnte nicht angewendet werden.'),
          );
        },
      });
  }

  // -----------------------------------------------------------------
  // Save mapping modal
  // -----------------------------------------------------------------

  protected openSaveMappingModal(): void {
    this.saveMappingName = this.mappingName || '';
    this.saveMappingDescription = '';
    this.showSaveMappingModal = true;
  }

  protected cancelSaveMapping(): void {
    this.showSaveMappingModal = false;
  }

  protected confirmSaveMapping(): void {
    const name = this.saveMappingName.trim();
    if (!name) {
      this.notifications.showError('Bitte einen Namen für das Mapping angeben.');
      return;
    }
    const previewObj = this.preview();
    if (!previewObj) {
      return;
    }
    const circuit_columns: Record<string, string> = {};
    for (const field of this.knownFields) {
      const src = this.mappingState[field];
      if (src && src.trim().length > 0) {
        circuit_columns[field] = src;
      }
    }
    this.busy.set(true);
    this.heating
      .saveMapping(name, {
        description: this.saveMappingDescription || null,
        importer_source: previewObj.source || 'generic_table',
        column_map: { circuit_columns, design_overrides: {} },
      })
      .subscribe({
        next: () => {
          this.busy.set(false);
          this.showSaveMappingModal = false;
          this.notifications.showMessage(`Mapping "${name}" gespeichert.`);
          this.heating.listMappings().subscribe({
            next: (list) => this.mappings.set(list),
            error: () => undefined,
          });
        },
        error: (response) => {
          this.busy.set(false);
          this.notifications.showError(
            formatHttpError(response, 'Mapping konnte nicht gespeichert werden.'),
          );
        },
      });
  }

  // -----------------------------------------------------------------
  // Design overrides (top form on preview step)
  // -----------------------------------------------------------------

  protected updateDesignField(
    key:
      | 'system_type'
      | 'supply_temp_c'
      | 'return_temp_c'
      | 'delta_t_k'
      | 'pump_head_pa'
      | 'total_volume_flow_lph'
      | 'pump_model'
      | 'notes',
    value: string,
  ): void {
    const current = this.preview();
    if (!current) {
      return;
    }
    const next: HeatingDesignImportPreview = {
      ...current,
      design: { ...current.design },
    };
    const trimmed = value.trim();
    if (
      key === 'supply_temp_c' ||
      key === 'return_temp_c' ||
      key === 'delta_t_k' ||
      key === 'pump_head_pa' ||
      key === 'total_volume_flow_lph'
    ) {
      next.design[key] = trimmed === '' ? null : Number(trimmed);
    } else {
      next.design[key] = trimmed === '' ? null : trimmed;
    }
    this.preview.set(next);
  }

  protected previewCircuitsForDisplay(): HeatingCircuitPreview[] {
    const p = this.preview();
    if (!p) {
      return [];
    }
    return p.circuits.slice(0, 20);
  }

  protected warningSeverity(): 'none' | 'mild' | 'strong' {
    const count = this.preview()?.warnings.length ?? 0;
    if (count === 0) return 'none';
    if (count <= 3) return 'mild';
    return 'strong';
  }

  // -----------------------------------------------------------------
  // Step 3 — Confirm / persist
  // -----------------------------------------------------------------

  protected confirmImport(): void {
    const previewObj = this.preview();
    if (!previewObj) {
      return;
    }
    this.busy.set(true);
    this.notifications.clear();
    this.heating.importConfirm(this.slug, previewObj).subscribe({
      next: () => {
        this.busy.set(false);
        this.notifications.showMessage('Strangberechnung wurde importiert.');
        this.router.navigate(['/projects', this.slug]);
      },
      error: (response) => {
        this.busy.set(false);
        this.notifications.showError(
          formatHttpError(response, 'Import konnte nicht abgeschlossen werden.'),
        );
      },
    });
  }

  protected backToSelect(): void {
    this.step.set('select');
    this.preview.set(null);
  }

  // -----------------------------------------------------------------
  // Helpers for the template
  // -----------------------------------------------------------------

  protected formatNumber(value: number | null | undefined, digits = 1): string {
    if (value === null || value === undefined || Number.isNaN(value)) {
      return '—';
    }
    return new Intl.NumberFormat('de-DE', {
      minimumFractionDigits: 0,
      maximumFractionDigits: digits,
    }).format(value);
  }

  protected formatText(value: string | null | undefined): string {
    if (value === null || value === undefined || value === '') {
      return '—';
    }
    return value;
  }
}
