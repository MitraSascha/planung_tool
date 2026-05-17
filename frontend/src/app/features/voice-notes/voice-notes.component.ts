import { CommonModule } from '@angular/common';
import { Component, Input, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import {
  VOICE_NOTE_INTENT_LABELS,
  VoiceNoteIntent,
  VoiceNoteRead,
} from '../../core/models/voice-note.model';
import { NotificationService } from '../../core/services/notification.service';
import { VoiceNoteService } from '../../core/services/voice-note.service';
import { formatHttpError } from '../../core/services/error-format';
import { formatDateTime } from '../../shared/utils/format';
import { VoiceRecorderComponent } from '../../shared/components/voice-recorder/voice-recorder.component';

@Component({
  selector: 'app-voice-notes',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, VoiceRecorderComponent],
  templateUrl: './voice-notes.component.html',
  styleUrl: './voice-notes.component.scss',
})
export class VoiceNotesComponent implements OnInit, OnDestroy {
  private readonly voiceNoteService = inject(VoiceNoteService);
  private readonly notifications = inject(NotificationService);

  @Input() slug!: string;

  protected readonly notes = signal<VoiceNoteRead[]>([]);
  protected readonly loading = signal(false);
  protected readonly editingId = signal<number | null>(null);
  protected readonly editingTranscript = signal('');

  protected readonly intentLabels = VOICE_NOTE_INTENT_LABELS;
  protected readonly formatDateTime = formatDateTime;

  private pollTimer: number | null = null;

  ngOnInit(): void {
    this.reload();
  }

  ngOnDestroy(): void {
    this.stopPolling();
  }

  protected reload(): void {
    this.loading.set(true);
    this.voiceNoteService.list(this.slug).subscribe({
      next: (notes) => {
        this.notes.set(notes);
        this.loading.set(false);
        this.maybeStartPolling();
      },
      error: (response) => {
        this.loading.set(false);
        this.notifications.showError(
          formatHttpError(response, 'Sprachnotizen konnten nicht geladen werden.'),
        );
      },
    });
  }

  protected onVoiceNoteSaved(note: VoiceNoteRead): void {
    this.notes.update((current) => [note, ...current]);
    this.maybeStartPolling();
  }

  protected refreshNote(id: number): void {
    this.voiceNoteService.pollStatus(this.slug, id).subscribe({
      next: (note) => {
        this.notes.update((current) =>
          current.map((existing) => (existing.id === note.id ? note : existing)),
        );
      },
      error: () => {
        // ignore — manuelles Refresh
      },
    });
  }

  protected deleteNote(note: VoiceNoteRead): void {
    if (!confirm('Sprachnotiz wirklich loeschen?')) {
      return;
    }
    this.voiceNoteService.delete(this.slug, note.id).subscribe({
      next: () => {
        this.notes.update((current) => current.filter((entry) => entry.id !== note.id));
        this.notifications.showMessage('Sprachnotiz geloescht.');
      },
      error: (response) =>
        this.notifications.showError(formatHttpError(response, 'Loeschen fehlgeschlagen.')),
    });
  }

  protected startEdit(note: VoiceNoteRead): void {
    this.editingId.set(note.id);
    this.editingTranscript.set(note.transcript ?? '');
  }

  protected cancelEdit(): void {
    this.editingId.set(null);
    this.editingTranscript.set('');
  }

  protected saveEdit(note: VoiceNoteRead): void {
    const transcript = this.editingTranscript().trim();
    this.voiceNoteService
      .update(this.slug, note.id, { transcript })
      .subscribe({
        next: (updated) => {
          this.notes.update((current) =>
            current.map((existing) => (existing.id === updated.id ? updated : existing)),
          );
          this.cancelEdit();
          this.notifications.showMessage('Transkript aktualisiert.');
        },
        error: (response) =>
          this.notifications.showError(formatHttpError(response, 'Speichern fehlgeschlagen.')),
      });
  }

  protected updateIntent(note: VoiceNoteRead, intent: VoiceNoteIntent): void {
    this.voiceNoteService.update(this.slug, note.id, { intent }).subscribe({
      next: (updated) => {
        this.notes.update((current) =>
          current.map((existing) => (existing.id === updated.id ? updated : existing)),
        );
      },
      error: (response) =>
        this.notifications.showError(formatHttpError(response, 'Aenderung fehlgeschlagen.')),
    });
  }

  private maybeStartPolling(): void {
    const hasPending = this.notes().some((note) => note.transcription_status === 'pending');
    if (hasPending) {
      this.startPolling();
    } else {
      this.stopPolling();
    }
  }

  private startPolling(): void {
    if (this.pollTimer !== null) {
      return;
    }
    this.pollTimer = window.setInterval(() => this.pollPending(), 5000);
  }

  private stopPolling(): void {
    if (this.pollTimer !== null) {
      window.clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  private pollPending(): void {
    const pending = this.notes().filter((note) => note.transcription_status === 'pending');
    if (pending.length === 0) {
      this.stopPolling();
      return;
    }
    for (const note of pending) {
      this.refreshNote(note.id);
    }
    // nach kurzer Zeit erneut pruefen
    setTimeout(() => this.maybeStartPolling(), 500);
  }
}
