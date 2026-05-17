import { CommonModule } from '@angular/common';
import {
  Component,
  Input,
  OnChanges,
  OnInit,
  SimpleChanges,
  computed,
  inject,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { HeatingDesignRead } from '../../core/models';
import { HeatingService } from '../../core/services/heating.service';
import { NotificationService } from '../../core/services/notification.service';
import { formatHttpError } from '../../core/services/error-format';
import { formatDateTime } from '../../shared/utils/format';

const SOURCE_LABELS: Record<string, string> = {
  manual: 'Manuell erfasst',
  viptool_xlsx: 'VIPtool XLSX',
  viptool_ifc: 'VIPtool IFC',
  generic_table: 'Tabelle (generisch)',
  ifc: 'IFC-Modell',
};

@Component({
  selector: 'app-heating-design',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './heating-design.component.html',
  styleUrl: './heating-design.component.scss',
})
export class HeatingDesignComponent implements OnInit, OnChanges {
  private readonly heating = inject(HeatingService);
  private readonly notifications = inject(NotificationService);

  @Input() slug!: string;

  protected readonly loading = signal(false);
  protected readonly loaded = signal(false);
  protected readonly design = signal<HeatingDesignRead | null>(null);

  protected readonly formatDateTime = formatDateTime;

  protected readonly sortedCircuits = computed(() => {
    const value = this.design();
    if (!value) {
      return [];
    }
    return [...value.circuits].sort((a, b) => a.position - b.position);
  });

  ngOnInit(): void {
    if (this.slug) {
      this.reload();
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['slug'] && !changes['slug'].firstChange && this.slug) {
      this.reload();
    }
  }

  protected reload(): void {
    this.loading.set(true);
    this.heating.get(this.slug).subscribe({
      next: (design) => {
        this.design.set(design);
        this.loaded.set(true);
        this.loading.set(false);
      },
      error: (response) => {
        this.loading.set(false);
        this.loaded.set(true);
        this.notifications.showError(
          formatHttpError(
            response,
            'Strangberechnung konnte nicht geladen werden.',
          ),
        );
      },
    });
  }

  protected sourceLabel(source: string): string {
    return SOURCE_LABELS[source] ?? source;
  }

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
