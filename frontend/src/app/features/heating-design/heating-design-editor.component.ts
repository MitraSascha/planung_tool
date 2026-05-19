import { CommonModule } from '@angular/common';
import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import {
  HeatingCircuitWrite,
  HeatingDesignRead,
  HeatingDesignWrite,
} from '../../core/models';
import { HeatingService } from '../../core/services/heating.service';
import { NotificationService } from '../../core/services/notification.service';
import { formatHttpError } from '../../core/services/error-format';

interface CircuitRow {
  position: number;
  strand: string;
  room: string;
  floor: string;
  radiator_type: string;
  heat_load_w: number | null;
  volume_flow_lph: number | null;
  pressure_drop_pa: number | null;
  pipe_length_m: number | null;
  valve_type: string;
  valve_preset: string;
  kv_value: number | null;
  notes: string;
}

interface DesignForm {
  system_type: string;
  supply_temp_c: number | null;
  return_temp_c: number | null;
  delta_t_k: number | null;
  pump_head_pa: number | null;
  total_volume_flow_lph: number | null;
  pump_model: string;
  notes: string;
}

const SYSTEM_TYPE_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: '', label: '(nicht angegeben)' },
  { value: 'radiator', label: 'Heizkörper' },
  { value: 'underfloor', label: 'Fußbodenheizung' },
  { value: 'mixed', label: 'Mischsystem' },
];

@Component({
  selector: 'app-heating-design-editor',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './heating-design-editor.component.html',
  styleUrl: './heating-design-editor.component.scss',
})
export class HeatingDesignEditorComponent implements OnInit {
  private readonly heating = inject(HeatingService);
  private readonly notifications = inject(NotificationService);
  private readonly router = inject(Router);

  @Input() slug!: string;

  protected readonly loading = signal(false);
  protected readonly saving = signal(false);
  protected readonly systemTypeOptions = SYSTEM_TYPE_OPTIONS;

  /** Felder, die aus dem Import nicht befüllt wurden — Hinweis für den User
   *  damit er weiß, welche Werte er von Hand ergänzen muss. */
  protected missingPlantFields(): string[] {
    const fields: Array<[string, unknown]> = [
      ['System', this.design.system_type],
      ['Vorlauf', this.design.supply_temp_c],
      ['Rücklauf', this.design.return_temp_c],
      ['Volumenstrom', this.design.total_volume_flow_lph],
      ['Pumpenförderhöhe', this.design.pump_head_pa],
      ['Pumpenmodell', this.design.pump_model],
    ];
    return fields
      .filter(([, v]) => v == null || v === '' || (typeof v === 'number' && Number.isNaN(v)))
      .map(([name]) => name);
  }

  protected design: DesignForm = this.emptyDesign();
  protected circuits: CircuitRow[] = [];

  // Preserved metadata when editing an existing record (e.g. previous source).
  protected existing: HeatingDesignRead | null = null;

  ngOnInit(): void {
    if (!this.slug) {
      return;
    }
    this.loading.set(true);
    this.heating.get(this.slug).subscribe({
      next: (existing) => {
        this.loading.set(false);
        if (existing) {
          this.existing = existing;
          this.design = {
            system_type: existing.system_type ?? '',
            supply_temp_c: existing.supply_temp_c,
            return_temp_c: existing.return_temp_c,
            delta_t_k: existing.delta_t_k,
            pump_head_pa: existing.pump_head_pa,
            total_volume_flow_lph: existing.total_volume_flow_lph,
            pump_model: existing.pump_model ?? '',
            notes: existing.notes ?? '',
          };
          this.circuits = [...existing.circuits]
            .sort((a, b) => a.position - b.position)
            .map((c, idx) => ({
              position: idx + 1,
              strand: c.strand ?? '',
              room: c.room ?? '',
              floor: c.floor ?? '',
              radiator_type: c.radiator_type ?? '',
              heat_load_w: c.heat_load_w,
              volume_flow_lph: c.volume_flow_lph,
              pressure_drop_pa: c.pressure_drop_pa,
              pipe_length_m: c.pipe_length_m,
              valve_type: c.valve_type ?? '',
              valve_preset: c.valve_preset ?? '',
              kv_value: c.kv_value,
              notes: c.notes ?? '',
            }));
        } else {
          this.addRow();
        }
      },
      error: (response) => {
        this.loading.set(false);
        this.notifications.showError(
          formatHttpError(response, 'Strangberechnung konnte nicht geladen werden.'),
        );
      },
    });
  }

  protected addRow(): void {
    this.circuits = [
      ...this.circuits,
      {
        position: this.circuits.length + 1,
        strand: '',
        room: '',
        floor: '',
        radiator_type: '',
        heat_load_w: null,
        volume_flow_lph: null,
        pressure_drop_pa: null,
        pipe_length_m: null,
        valve_type: '',
        valve_preset: '',
        kv_value: null,
        notes: '',
      },
    ];
  }

  protected removeRow(index: number): void {
    this.circuits = this.circuits.filter((_, i) => i !== index);
    this.circuits.forEach((row, i) => {
      row.position = i + 1;
    });
  }

  protected moveRow(index: number, direction: -1 | 1): void {
    const target = index + direction;
    if (target < 0 || target >= this.circuits.length) {
      return;
    }
    const next = [...this.circuits];
    const tmp = next[index];
    next[index] = next[target];
    next[target] = tmp;
    next.forEach((row, i) => {
      row.position = i + 1;
    });
    this.circuits = next;
  }

  protected trackByIndex(index: number): number {
    return index;
  }

  protected save(): void {
    const payload: HeatingDesignWrite = {
      system_type: this.design.system_type.trim() || null,
      supply_temp_c: this.coerceNumber(this.design.supply_temp_c),
      return_temp_c: this.coerceNumber(this.design.return_temp_c),
      delta_t_k: this.coerceNumber(this.design.delta_t_k),
      pump_head_pa: this.coerceNumber(this.design.pump_head_pa),
      total_volume_flow_lph: this.coerceNumber(this.design.total_volume_flow_lph),
      pump_model: this.design.pump_model.trim() || null,
      notes: this.design.notes.trim() || null,
      source: 'manual',
      source_file: null,
      circuits: this.circuits.map<HeatingCircuitWrite>((row, idx) => ({
        position: idx + 1,
        strand: row.strand.trim() || null,
        room: row.room.trim() || null,
        floor: row.floor.trim() || null,
        radiator_type: row.radiator_type.trim() || null,
        heat_load_w: this.coerceNumber(row.heat_load_w),
        volume_flow_lph: this.coerceNumber(row.volume_flow_lph),
        pressure_drop_pa: this.coerceNumber(row.pressure_drop_pa),
        pipe_length_m: this.coerceNumber(row.pipe_length_m),
        valve_type: row.valve_type.trim() || null,
        valve_preset: row.valve_preset.trim() || null,
        kv_value: this.coerceNumber(row.kv_value),
        notes: row.notes.trim() || null,
      })),
    };

    this.saving.set(true);
    this.notifications.clear();
    this.heating.upsert(this.slug, payload).subscribe({
      next: () => {
        this.saving.set(false);
        this.notifications.showMessage('Strangberechnung wurde gespeichert.');
        this.router.navigate(['/projects', this.slug]);
      },
      error: (response) => {
        this.saving.set(false);
        this.notifications.showError(
          formatHttpError(response, 'Strangberechnung konnte nicht gespeichert werden.'),
        );
      },
    });
  }

  private coerceNumber(value: number | string | null | undefined): number | null {
    if (value === null || value === undefined) {
      return null;
    }
    if (typeof value === 'number') {
      return Number.isFinite(value) ? value : null;
    }
    const trimmed = String(value).trim();
    if (trimmed === '') {
      return null;
    }
    const parsed = Number(trimmed);
    return Number.isFinite(parsed) ? parsed : null;
  }

  private emptyDesign(): DesignForm {
    return {
      system_type: '',
      supply_temp_c: null,
      return_temp_c: null,
      delta_t_k: null,
      pump_head_pa: null,
      total_volume_flow_lph: null,
      pump_model: '',
      notes: '',
    };
  }
}
