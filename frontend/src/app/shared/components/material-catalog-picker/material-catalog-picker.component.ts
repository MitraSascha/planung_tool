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

const TYPE_LABELS: Record<string, string> = {
  rohr: 'Rohre',
  ventil: 'Ventile',
  formstueck: 'Formstücke',
  sonstiges: 'Sonstiges',
};

// Anzeige-Reihenfolge der Typ-Chips — explizit, weil alphabetisch
// (formstueck/rohr/sonstiges/ventil) keinen Sinn macht.
const TYPE_ORDER = ['rohr', 'ventil', 'formstueck', 'sonstiges'];

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
  /** Typen die in der aktuell gewählten Kategorie Treffer haben. */
  protected readonly types = signal<string[]>([]);
  /** Aktiver Typ-Filter. `null` = „Alle Typen". */
  protected readonly activeType = signal<string | null>(null);

  private readonly query$ = new BehaviorSubject<string>('');
  private readonly category$ = new BehaviorSubject<string | null>(null);
  private readonly type$ = new BehaviorSubject<string | null>(null);

  constructor() {
    // Body-Scroll-Lock wenn Sheet offen ist
    effect(() => {
      if (typeof document === 'undefined') return;
      document.body.style.overflow = this.open() ? 'hidden' : '';
    });

    // Such-Stream: kombiniert Volltext-Query (debounced) mit Kategorie- und
    // Typ-Filter (sofort wirksam). Chip-Switches sollen nicht 250ms warten.
    combineLatest([
      this.query$.pipe(debounceTime(250), distinctUntilChanged()),
      this.category$.pipe(distinctUntilChanged()),
      this.type$.pipe(distinctUntilChanged()),
    ])
      .pipe(
        switchMap(([q, cat, typ]) => {
          this.busy.set(true);
          this.error.set(null);
          return this.catalog.list(q, cat, typ, 200).pipe(
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

  /** Lädt die verfügbaren Typen für die aktive Kategorie. So zeigt der
   *  Picker für „Isolierung" nicht „Ventile"-Chips, weil dort keiner ist. */
  private refreshTypes(): void {
    this.catalog.listTypes(this.activeCategory()).subscribe({
      next: (rows) => {
        const ordered = TYPE_ORDER.filter((t) => rows.includes(t));
        this.types.set(ordered);
        // Wenn der aktive Typ in der neuen Kategorie nicht mehr existiert,
        // zurücksetzen.
        const at = this.activeType();
        if (at && !rows.includes(at)) {
          this.activeType.set(null);
          this.type$.next(null);
        }
      },
      error: () => this.types.set([]),
    });
  }

  protected openSheet(): void {
    this.query.set('');
    this.activeCategory.set(null);
    this.activeType.set(null);
    this.category$.next(null);
    this.type$.next(null);
    this.open.set(true);
    this.query$.next(''); // Initial-Laden alphabetisch
    if (this.categories().length === 0) {
      // Kategorien-Liste einmal beim ersten Öffnen holen.
      this.catalog.listCategories().subscribe({
        next: (rows) => this.categories.set(rows),
        error: () => this.categories.set([]),
      });
    }
    this.refreshTypes();
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
    // Nach Kategorie-Wechsel die verfügbaren Typen neu laden.
    this.refreshTypes();
  }

  protected setType(t: string | null): void {
    this.activeType.set(t);
    this.type$.next(t);
  }

  protected categoryLabel(cat: string): string {
    return CATEGORY_LABELS[cat] ?? cat;
  }

  protected typeLabel(t: string): string {
    return TYPE_LABELS[t] ?? t;
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
