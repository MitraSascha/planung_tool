import { CommonModule } from '@angular/common';
import { Component, computed, input } from '@angular/core';

import { GenerationRunRead } from '../../../core/models';

type Phase = 'ingest' | 'generate' | 'done' | 'failed';

const INGEST_STATUSES = new Set(['queued', 'created', 'filtering']);
const GENERATE_STATUSES = new Set(['generating', 'running']);
const PUBLISH_STATUSES = new Set(['publishing']);
const DONE_STATUSES = new Set(['completed', 'succeeded', 'published']);
const FAILED_STATUSES = new Set([
  'failed',
  'failed_partial',
  'generation_failed',
  'generation_failed_partial',
  'publish_failed',
]);

@Component({
  selector: 'app-run-progress',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './run-progress.component.html',
  styleUrl: './run-progress.component.scss',
})
export class RunProgressComponent {
  readonly run = input.required<GenerationRunRead>();

  protected readonly phase = computed<Phase>(() => {
    const status = this.run().status;
    if (FAILED_STATUSES.has(status)) return 'failed';
    if (DONE_STATUSES.has(status)) return 'done';
    if (PUBLISH_STATUSES.has(status) || GENERATE_STATUSES.has(status)) {
      return 'generate';
    }
    return 'ingest';
  });

  protected readonly ingestPercent = computed<number>(() => {
    const p = this.phase();
    return p === 'ingest' ? 0 : 100;
  });

  protected readonly generatePercent = computed<number>(() => {
    const p = this.phase();
    if (p === 'ingest') return 0;
    if (p === 'done') return 100;
    if (p === 'failed') {
      // Failed runs: show how far the bar got based on counts.
      const r = this.run();
      return r.progress_total > 0
        ? Math.min(100, Math.round((r.progress_current / r.progress_total) * 100))
        : 0;
    }
    const r = this.run();
    if (r.status === 'publishing') return 100;
    if (r.progress_total <= 0) return 0;
    return Math.min(100, Math.round((r.progress_current / r.progress_total) * 100));
  });

  protected readonly ingestActive = computed(() => this.phase() === 'ingest');
  protected readonly generateActive = computed(() => this.phase() === 'generate');
  protected readonly isDone = computed(() => this.phase() === 'done');
  protected readonly isFailed = computed(() => this.phase() === 'failed');

  protected readonly ingestDetail = computed<string>(() => {
    const p = this.phase();
    if (p === 'ingest') {
      return this.run().current_step || 'Bereite Daten vor …';
    }
    return 'abgeschlossen';
  });

  protected readonly generateDetail = computed<string>(() => {
    const r = this.run();
    if (this.phase() === 'ingest') return 'wartet';
    if (this.phase() === 'done') return 'abgeschlossen';
    if (r.status === 'publishing') return 'Veröffentlichen…';
    return `${r.progress_current} / ${r.progress_total} Tasks`;
  });
}
