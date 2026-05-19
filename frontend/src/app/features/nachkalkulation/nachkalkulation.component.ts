import { CommonModule } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { formatHttpError } from '../../core/services/error-format';
import { NotificationService } from '../../core/services/notification.service';
import {
  NachkalkulationResult,
  NachkalkulationSection,
  NachkalkulationService,
} from '../../core/services/nachkalkulation.service';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';

@Component({
  selector: 'app-nachkalkulation',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, EmptyStateComponent],
  templateUrl: './nachkalkulation.component.html',
  styleUrl: './nachkalkulation.component.scss',
})
export class NachkalkulationComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly service = inject(NachkalkulationService);
  private readonly notifications = inject(NotificationService);

  protected readonly slug = signal<string>('');
  protected readonly busy = signal<boolean>(false);
  protected readonly result = signal<NachkalkulationResult | null>(null);

  /** Aktuelle Filterauswahl: section_number als String („all" = alle). */
  protected readonly sectionFilter = signal<string>('all');

  /** Welche Sektionen sind im Akkordeon eingeklappt? Standard: alle offen. */
  protected readonly collapsed = signal<Set<string>>(new Set());

  protected readonly sectionOptions = computed(() => {
    const res = this.result();
    if (!res) return [];
    return res.sections.map((s) => ({
      key: this.sectionKey(s),
      label:
        s.section_number != null
          ? `Abschnitt ${s.section_number}${s.section_name ? ' · ' + s.section_name : ''}`
          : 'Ohne Zuordnung',
      count: s.item_count,
    }));
  });

  protected readonly filteredSections = computed<NachkalkulationSection[]>(() => {
    const res = this.result();
    if (!res) return [];
    const filter = this.sectionFilter();
    if (filter === 'all') return res.sections;
    return res.sections.filter((s) => this.sectionKey(s) === filter);
  });

  ngOnInit(): void {
    this.route.paramMap.subscribe((params) => {
      const slug = params.get('slug') || '';
      this.slug.set(slug);
      if (slug) this.load(slug);
    });
  }

  protected load(slug: string): void {
    this.busy.set(true);
    this.service.get(slug).subscribe({
      next: (res) => {
        this.result.set(res);
        this.busy.set(false);
        // Initial alles offen
        this.collapsed.set(new Set());
      },
      error: (err) => {
        this.busy.set(false);
        this.notifications.showError(
          formatHttpError(err, 'Nachkalkulation konnte nicht geladen werden.'),
        );
      },
    });
  }

  protected sectionKey(section: NachkalkulationSection): string {
    return section.section_number == null ? 'none' : String(section.section_number);
  }

  protected isCollapsed(section: NachkalkulationSection): boolean {
    return this.collapsed().has(this.sectionKey(section));
  }

  protected toggleSection(section: NachkalkulationSection): void {
    const key = this.sectionKey(section);
    const next = new Set(this.collapsed());
    if (next.has(key)) next.delete(key);
    else next.add(key);
    this.collapsed.set(next);
  }

  protected onSectionFilterChange(value: string): void {
    this.sectionFilter.set(value);
  }

  protected exportCsv(): void {
    const slug = this.slug();
    if (!slug) return;
    this.service.csv(slug).subscribe({
      next: (blob) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `nachkalkulation_${slug}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
      },
      error: (err) => {
        this.notifications.showError(
          formatHttpError(err, 'CSV-Export fehlgeschlagen.'),
        );
      },
    });
  }

  protected formatEur(value: number | null | undefined): string {
    if (value == null) return '–';
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
      maximumFractionDigits: 2,
    }).format(value);
  }

  protected formatNum(value: number | null | undefined, digits = 2): string {
    if (value == null) return '–';
    return new Intl.NumberFormat('de-DE', {
      maximumFractionDigits: digits,
      minimumFractionDigits: digits === 0 ? 0 : 0,
    }).format(value);
  }

  protected sectionLabel(section: NachkalkulationSection): string {
    if (section.section_number == null) return 'Ohne Zuordnung';
    return `Abschnitt ${section.section_number}${
      section.section_name ? ' · ' + section.section_name : ''
    }`;
  }
}
