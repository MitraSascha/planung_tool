import { CommonModule } from '@angular/common';
import { Component, computed, input } from '@angular/core';

import { HoursStatus } from '../../../core/models';

/**
 * Range-Bar für Stunden Soll/Ist. Drei Modi:
 *  - `under`/`on_track`: Ist-Balken bis %-Wert, restlicher Raum = Puffer
 *  - `over`: Voller Soll-Balken + roter Overshoot-Streifen rechts daneben
 *  - `unknown`: kein Soll hinterlegt → grauer Hinweis
 *
 * Wird benutzt für die Gesamtansicht und pro Bauabschnitt. Kompakter Modus
 * für Dashboards (`compact=true`) blendet die Sub-Zeile aus und zeigt nur
 * Bar + Werte rechts.
 */
@Component({
  selector: 'app-hours-progress',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './hours-progress.component.html',
  styleUrl: './hours-progress.component.scss',
})
export class HoursProgressComponent {
  readonly label = input<string>('');
  readonly planned = input<number | null>(null);
  readonly ist = input<number>(0);
  readonly status = input<HoursStatus>('unknown');
  readonly compact = input<boolean>(false);

  /** Anteil des Soll-Balkens (max 100). Bei Überschreitung füllt er voll
   *  und der Overshoot-Streifen kommt als zweite Bar dazu. */
  protected readonly sollFillPercent = computed(() => {
    const p = this.planned();
    const i = this.ist();
    if (!p || p <= 0) return 0;
    return Math.min(100, (i / p) * 100);
  });

  /** Overshoot-Anteil als Prozent des Soll (kann beliebig groß sein, wird
   *  visuell auf 100% gecappt damit die Bar nicht aus dem Layout läuft). */
  protected readonly overshootPercent = computed(() => {
    const p = this.planned();
    const i = this.ist();
    if (!p || p <= 0) return 0;
    if (i <= p) return 0;
    return Math.min(100, ((i - p) / p) * 100);
  });

  protected readonly delta = computed(() => {
    const p = this.planned();
    const i = this.ist();
    if (p == null) return null;
    return Math.round((i - p) * 10) / 10;
  });

  protected readonly percent = computed(() => {
    const p = this.planned();
    const i = this.ist();
    if (!p || p <= 0) return null;
    return Math.round((i / p) * 1000) / 10;
  });

  protected fmt(v: number | null | undefined): string {
    if (v == null) return '—';
    if (Number.isInteger(v)) return String(v);
    return v.toFixed(1).replace('.', ',');
  }
}
