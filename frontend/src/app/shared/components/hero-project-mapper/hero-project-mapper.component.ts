import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  Output,
  effect,
  inject,
  input,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subject, debounceTime, distinctUntilChanged, of, switchMap, catchError } from 'rxjs';

import { HeroProjectHit, HeroService } from '../../../core/services/hero.service';
import { NotificationService } from '../../../core/services/notification.service';
import { formatHttpError } from '../../../core/services/error-format';

/**
 * Kleines Admin-UI zum Verknüpfen Planung-Tool-Projekt ↔ HERO-ProjectMatch.
 *
 * Verwendung im Project-Detail-Panel (admin-only):
 *   ```html
 *   <app-hero-project-mapper
 *     [slug]="project.slug"
 *     [currentMappingId]="project.hero_project_match_id ?? null"
 *     (mapped)="reload()">
 *   </app-hero-project-mapper>
 *   ```
 *
 * UX:
 *   - Wenn schon gemappt: zeigt die ID + Button „Verknüpfung lösen"
 *   - Sonst: Suchfeld → GET /api/hero/search-projects → Klick auf Treffer
 *     → PATCH /api/hero/projects/{slug}/mapping.
 */
@Component({
  selector: 'app-hero-project-mapper',
  standalone: true,
  imports: [CommonModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './hero-project-mapper.component.html',
  styleUrl: './hero-project-mapper.component.scss',
})
export class HeroProjectMapperComponent {
  private readonly hero = inject(HeroService);
  private readonly notifications = inject(NotificationService);

  readonly slug = input.required<string>();
  readonly currentMappingId = input<number | null>(null);

  @Output() readonly mapped = new EventEmitter<number | null>();

  protected readonly searchQuery = signal('');
  protected readonly hits = signal<HeroProjectHit[]>([]);
  protected readonly busy = signal(false);
  protected readonly saving = signal(false);

  private readonly query$ = new Subject<string>();

  constructor() {
    this.query$
      .pipe(
        debounceTime(280),
        distinctUntilChanged(),
        switchMap((q) => {
          if (!q || q.trim().length < 2) {
            this.busy.set(false);
            return of([] as HeroProjectHit[]);
          }
          this.busy.set(true);
          return this.hero.searchProjects(q.trim(), 20).pipe(
            catchError((err) => {
              this.notifications.showError(
                formatHttpError(err, 'HERO-Suche fehlgeschlagen.'),
              );
              return of([] as HeroProjectHit[]);
            }),
          );
        }),
      )
      .subscribe((rows) => {
        this.busy.set(false);
        this.hits.set(rows);
      });

    // Beim Mapping-Wechsel der Quelle die Such-Ergebnisse zurücksetzen
    effect(() => {
      this.currentMappingId();
      this.hits.set([]);
      this.searchQuery.set('');
    });
  }

  protected onQueryChange(value: string): void {
    this.searchQuery.set(value);
    this.query$.next(value);
  }

  protected pick(hit: HeroProjectHit): void {
    if (this.saving()) return;
    this.saving.set(true);
    this.hero.setProjectMapping(this.slug(), hit.id).subscribe({
      next: (res) => {
        this.saving.set(false);
        this.notifications.showMessage(
          `Verknüpft mit HERO „${hit.name}" (#${hit.id}).`,
        );
        this.mapped.emit(res.hero_project_match_id);
      },
      error: (err) => {
        this.saving.set(false);
        this.notifications.showError(
          formatHttpError(err, 'Verknüpfung fehlgeschlagen.'),
        );
      },
    });
  }

  protected unlink(): void {
    if (this.saving()) return;
    this.saving.set(true);
    this.hero.setProjectMapping(this.slug(), null).subscribe({
      next: () => {
        this.saving.set(false);
        this.notifications.showMessage('HERO-Verknüpfung entfernt.');
        this.mapped.emit(null);
      },
      error: (err) => {
        this.saving.set(false);
        this.notifications.showError(
          formatHttpError(err, 'Entfernen fehlgeschlagen.'),
        );
      },
    });
  }

  protected formatHit(h: HeroProjectHit): string {
    const parts = [h.name];
    if (h.project_nr) parts.push(`#${h.project_nr}`);
    if (h.customer?.full_name) parts.push(h.customer.full_name);
    if (h.current_project_match_status?.name) parts.push(h.current_project_match_status.name);
    return parts.join(' · ');
  }
}
