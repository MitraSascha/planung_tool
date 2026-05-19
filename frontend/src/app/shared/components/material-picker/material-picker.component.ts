import { CommonModule } from '@angular/common';
import {
  Component,
  EventEmitter,
  HostListener,
  Output,
  computed,
  effect,
  inject,
  input,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subject, of, switchMap, debounceTime, distinctUntilChanged, catchError } from 'rxjs';

import { ArticleHit, MaterialItem } from '../../../core/models';
import { MaterialService } from '../../../core/services/material.service';

interface MaterialGroup {
  label: string;
  sectionNumber: number | null;
  items: MaterialItem[];
}

type PickerMode = 'project' | 'artikelstamm';

/**
 * Mobile-tauglicher Material-Picker. Ersetzt native `<select>`-Dropdowns,
 * deren Optionen auf der Baustelle zu lang sind, um in einer Zeile
 * gleichzeitig Artikelname + Dimension + Maße + Mengen sichtbar zu lassen.
 *
 * UX:
 *  - Trigger-Button mit aktueller Auswahl (Name + Meta-Zeile) oder Placeholder
 *  - Klick öffnet ein Bottom-Sheet (auch auf Desktop — konsistent mit
 *    MoreDrawer) mit Suchfeld, gruppiert nach Bauabschnitt
 *  - Jede Item-Karte: Zeile 1 = voller Artikelname (max 3 Zeilen wrap),
 *    Zeile 2 = Einheit · Soll/Ist · Lager · Hinweis-Badges
 *  - Suche filtert case-insensitive auf name, unit, location
 *  - Tap auf Item: selectionChange emit, Sheet schließt
 *  - Escape oder Backdrop-Klick schließt
 */
@Component({
  selector: 'app-material-picker',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './material-picker.component.html',
  styleUrl: './material-picker.component.scss',
})
export class MaterialPickerComponent {
  readonly items = input<MaterialItem[]>([]);
  readonly selected = input<number | null>(null);
  readonly sections = input<readonly { number: number; name: string }[]>([]);
  readonly placeholder = input<string>('Material wählen …');
  /** Wenn true: nur Items des aktuellen Abschnitts oder unassigned. */
  readonly currentSection = input<number | null>(null);
  readonly disabled = input<boolean>(false);
  /** Projekt-Slug für die Artikelstamm-Suche & das Anlegen neuer Material-
   *  Items aus dem Großhandelskatalog. Wenn null/leer: Artikelstamm-Tab
   *  wird ausgeblendet. */
  readonly projectSlug = input<string | null>(null);

  @Output() selectionChange = new EventEmitter<number | null>();
  /** Wird gefeuert, nachdem ein Artikel aus dem Artikelstamm zum Projekt-
   *  Stamm hinzugefügt wurde. Eltern-Komponente sollte die Material-Liste
   *  neu laden, damit der neue Eintrag im normalen Picker erscheint. */
  @Output() materialAdded = new EventEmitter<{ id: number; name: string }>();

  private readonly materials = inject(MaterialService);

  protected readonly open = signal(false);
  protected readonly query = signal('');
  protected readonly showAll = signal(false);

  /** „project" = Filter über Projekt-Stamm. „artikelstamm" = Live-Suche
   *  in der externen DATANORM-DB für Ad-hoc-Käufe (Monteur holt Material,
   *  das nicht im Angebot war). */
  protected readonly mode = signal<PickerMode>('project');
  protected readonly artikelstammAvailable = signal<boolean>(false);
  protected readonly artikelstammResults = signal<ArticleHit[]>([]);
  protected readonly artikelstammSearching = signal<boolean>(false);
  protected readonly addingFromArtikelstamm = signal<string | null>(null);
  private readonly artikelstammQuery$ = new Subject<string>();

  constructor() {
    // Body-Scroll-Lock wenn Sheet offen ist
    effect(() => {
      if (typeof document === 'undefined') return;
      document.body.style.overflow = this.open() ? 'hidden' : '';
    });
    // Artikelstamm-Verfügbarkeit einmalig prüfen (Server kann ohne externe DB laufen)
    this.materials.isArtikelstammAvailable().subscribe({
      next: (r) => this.artikelstammAvailable.set(!!r.available),
      error: () => this.artikelstammAvailable.set(false),
    });
    // Debounced Live-Suche im Artikelstamm
    this.artikelstammQuery$
      .pipe(
        debounceTime(280),
        distinctUntilChanged(),
        switchMap((q) => {
          if (!q || q.trim().length < 2) {
            this.artikelstammSearching.set(false);
            return of([] as ArticleHit[]);
          }
          this.artikelstammSearching.set(true);
          return this.materials.searchArtikelstamm(q.trim(), 30).pipe(
            catchError(() => of([] as ArticleHit[])),
          );
        }),
      )
      .subscribe((results) => {
        this.artikelstammSearching.set(false);
        this.artikelstammResults.set(results);
      });
  }

  protected readonly selectedItem = computed<MaterialItem | null>(() => {
    const id = this.selected();
    if (id == null) return null;
    return this.items().find((m) => m.id === id) ?? null;
  });

  protected readonly visibleItems = computed<MaterialItem[]>(() => {
    const all = this.items();
    const sec = this.currentSection();
    if (this.showAll() || sec == null) return all;
    return all.filter((m) => m.section_number === sec || m.section_number == null);
  });

  protected readonly hiddenCount = computed(
    () => this.items().length - this.visibleItems().length,
  );

  protected readonly filteredGroups = computed<MaterialGroup[]>(() => {
    const q = this.query().trim().toLowerCase();
    const list = this.visibleItems();
    const matched = q
      ? list.filter((m) => {
          const haystack = [
            m.name,
            m.unit ?? '',
            m.location ?? '',
            m.note ?? '',
          ].join(' ').toLowerCase();
          return haystack.includes(q);
        })
      : list;

    const sectionsLookup = new Map(this.sections().map((s) => [s.number, s.name]));
    const buckets = new Map<number | null, MaterialItem[]>();
    for (const m of matched) {
      const key = m.section_number;
      const arr = buckets.get(key);
      if (arr) arr.push(m);
      else buckets.set(key, [m]);
    }
    return Array.from(buckets.entries())
      .sort(([a], [b]) => {
        if (a === b) return 0;
        if (a == null) return 1;
        if (b == null) return -1;
        return a - b;
      })
      .map(([sec, items]) => ({
        sectionNumber: sec,
        label: sec == null
          ? 'Ohne Abschnittszuordnung'
          : `Abschnitt ${sec}${sectionsLookup.has(sec) ? ' · ' + sectionsLookup.get(sec) : ''}`,
        items: items.slice().sort((x, y) => x.name.localeCompare(y.name, 'de')),
      }));
  });

  protected readonly totalMatches = computed(
    () => this.filteredGroups().reduce((n, g) => n + g.items.length, 0),
  );

  protected openPicker(): void {
    if (this.disabled()) return;
    this.query.set('');
    this.mode.set('project');
    this.artikelstammResults.set([]);
    this.open.set(true);
  }

  protected closePicker(): void {
    this.open.set(false);
  }

  protected setMode(m: PickerMode): void {
    this.mode.set(m);
    this.query.set('');
    this.artikelstammResults.set([]);
  }

  protected onQueryChange(value: string): void {
    this.query.set(value);
    if (this.mode() === 'artikelstamm') {
      this.artikelstammQuery$.next(value);
    }
  }

  protected pick(item: MaterialItem): void {
    this.selectionChange.emit(item.id);
    this.closePicker();
  }

  /** Artikel aus dem Artikelstamm in den Projekt-Material-Stamm übernehmen
   *  und sofort als ausgewählt setzen. Wird die Eltern-Komponente per
   *  ``materialAdded`` informieren, damit sie die Liste neu lädt. */
  protected pickFromArtikelstamm(hit: ArticleHit): void {
    if (this.addingFromArtikelstamm()) return;
    const slug = this.projectSlug();
    if (!slug) return;
    this.addingFromArtikelstamm.set(hit.artikelnummer);
    this.materials
      .createMaterialFromArtikelstamm(slug, {
        artikelnummer: hit.artikelnummer,
        section_number: this.currentSection() ?? null,
      })
      .subscribe({
        next: (resp) => {
          this.addingFromArtikelstamm.set(null);
          this.materialAdded.emit({
            id: resp.id,
            name: resp.name ?? (hit.kurztext1 ?? hit.artikelnummer),
          });
          this.selectionChange.emit(resp.id);
          this.closePicker();
        },
        error: () => {
          this.addingFromArtikelstamm.set(null);
        },
      });
  }

  /** Kompakter Anzeigetext für einen Artikelstamm-Treffer. */
  protected artikelTitle(a: ArticleHit): string {
    return [a.kurztext1, a.kurztext2].filter(Boolean).join(' ');
  }
  protected artikelHersteller(a: ArticleHit): string {
    return [a.hersteller, a.hersteller_artikelnummer].filter(Boolean).join(' · ');
  }

  protected clearSelection(event: Event): void {
    event.stopPropagation();
    this.selectionChange.emit(null);
  }

  protected toggleShowAll(): void {
    this.showAll.update((v) => !v);
  }

  protected isSelected(item: MaterialItem): boolean {
    return this.selected() === item.id;
  }

  protected restPiece(m: MaterialItem): string | null {
    if (m.soll_qty == null) return null;
    const ist = m.ist_qty ?? 0;
    const remaining = m.soll_qty - ist;
    if (remaining <= 0) return null;
    return remaining.toString();
  }

  @HostListener('document:keydown.escape')
  protected onEsc(): void {
    if (this.open()) this.closePicker();
  }
}
