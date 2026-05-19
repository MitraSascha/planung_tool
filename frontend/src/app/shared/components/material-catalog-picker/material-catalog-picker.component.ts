import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  HostListener,
  Output,
  effect,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subject, combineLatest, debounceTime, distinctUntilChanged, of, switchMap, catchError, BehaviorSubject } from 'rxjs';

import {
  MaterialCatalogEntry,
  MaterialCatalogService,
} from '../../../core/services/material-catalog.service';

const CATEGORY_LABELS: Record<string, string> = {
  standard: 'Standard',
  brandschutz: 'Brandschutz',
  isolierung: 'Isolierung',
};

/**
 * Bottom-Sheet zur Auswahl aus dem kuratierten Materialkatalog
 * (siehe ``backend/app/services/material_catalog.py``).
 *
 * UX:
 *   - Trigger-Button öffnet ein Bottom-Sheet mit Suchfeld + Live-Suche
 *     (debounced 250ms). Auch auf Desktop als Bottom-Sheet — konsistent mit
 *     MaterialPicker.
 *   - Server liefert alphabetisch sortiert; Frontend rendert die Hits.
 *   - Tap auf Item ⇒ ``selected`` Event, Sheet schließt.
 */
@Component({
  selector: 'app-material-catalog-picker',
  standalone: true,
  imports: [CommonModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './material-catalog-picker.component.html',
  styleUrl: './material-catalog-picker.component.scss',
})
export class MaterialCatalogPickerComponent {
  private readonly catalog = inject(MaterialCatalogService);

  @Output() readonly selected = new EventEmitter<MaterialCatalogEntry>();

  protected readonly open = signal(false);
  protected readonly query = signal('');
  protected readonly busy = signal(false);
  protected readonly results = signal<MaterialCatalogEntry[]>([]);
  protected readonly error = signal<string | null>(null);
  /** Verfügbare Kategorien (kommen vom Server beim ersten Öffnen). */
  protected readonly categories = signal<string[]>([]);
  /** Aktive Filter-Kategorie. `null` = „Alle anzeigen". */
  protected readonly activeCategory = signal<string | null>(null);

  private readonly query$ = new BehaviorSubject<string>('');
  private readonly category$ = new BehaviorSubject<string | null>(null);

  constructor() {
    // Body-Scroll-Lock wenn Sheet offen ist
    effect(() => {
      if (typeof document === 'undefined') return;
      document.body.style.overflow = this.open() ? 'hidden' : '';
    });

    // Such-Stream: kombiniert Volltext-Query (debounced) mit Kategorie-Filter
    // (sofort wirksam). Kategorie-Switches sollen nicht 250ms warten.
    combineLatest([
      this.query$.pipe(debounceTime(250), distinctUntilChanged()),
      this.category$.pipe(distinctUntilChanged()),
    ])
      .pipe(
        switchMap(([q, cat]) => {
          this.busy.set(true);
          this.error.set(null);
          return this.catalog.list(q, cat, 200).pipe(
            catchError(() => {
              this.error.set('Liste konnte nicht geladen werden.');
              return of([] as MaterialCatalogEntry[]);
            }),
          );
        }),
      )
      .subscribe((rows) => {
        this.busy.set(false);
        this.results.set(rows);
      });
  }

  protected openSheet(): void {
    this.query.set('');
    this.activeCategory.set(null);
    this.category$.next(null);
    this.open.set(true);
    this.query$.next(''); // Initial-Laden alphabetisch
    if (this.categories().length === 0) {
      // Kategorien-Liste einmal beim ersten Öffnen holen.
      this.catalog.listCategories().subscribe({
        next: (rows) => this.categories.set(rows),
        error: () => this.categories.set([]),
      });
    }
  }

  protected closeSheet(): void {
    this.open.set(false);
  }

  protected onQueryChange(value: string): void {
    this.query.set(value);
    this.query$.next(value);
  }

  protected setCategory(cat: string | null): void {
    this.activeCategory.set(cat);
    this.category$.next(cat);
  }

  protected categoryLabel(cat: string): string {
    return CATEGORY_LABELS[cat] ?? cat;
  }

  protected pick(entry: MaterialCatalogEntry): void {
    this.selected.emit(entry);
    this.closeSheet();
  }

  @HostListener('document:keydown.escape')
  protected onEsc(): void {
    if (this.open()) this.closeSheet();
  }

  protected trackById(_: number, e: MaterialCatalogEntry): number {
    return e.id;
  }

  protected formatPrice(p: number | null): string {
    if (p == null) return '';
    return `${p.toFixed(2).replace('.', ',')} €`;
  }
}
