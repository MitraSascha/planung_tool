import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  Input,
  OnDestroy,
  Output,
  inject,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';

import { VoiceNoteIntent, VoiceNoteRead } from '../../../core/models/voice-note.model';
import { NotificationService } from '../../../core/services/notification.service';
import { VoiceNoteService } from '../../../core/services/voice-note.service';
import { formatHttpError } from '../../../core/services/error-format';

type RecorderState = 'idle' | 'recording' | 'paused' | 'review' | 'uploading';

@Component({
  selector: 'app-voice-recorder',
  standalone: true,
  imports: [CommonModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './voice-recorder.component.html',
  styleUrl: './voice-recorder.component.scss',
})
export class VoiceRecorderComponent implements OnDestroy {
  private readonly voiceNoteService = inject(VoiceNoteService);
  private readonly notifications = inject(NotificationService);

  @Input({ required: true }) slug!: string;

  @Output() readonly voiceNoteSaved = new EventEmitter<VoiceNoteRead>();

  protected readonly state = signal<RecorderState>('idle');
  protected readonly elapsedSeconds = signal(0);
  protected readonly intent = signal<VoiceNoteIntent>('freitext');
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly previewUrl = signal<string | null>(null);

  private recorder: MediaRecorder | null = null;
  private mediaStream: MediaStream | null = null;
  private chunks: Blob[] = [];
  private startTimestampMs: number | null = null;
  private accumulatedMs = 0;
  private timerId: number | null = null;

  ngOnDestroy(): void {
    this.cleanupResources();
  }

  protected get supported(): boolean {
    return (
      typeof navigator !== 'undefined' &&
      !!navigator.mediaDevices &&
      typeof MediaRecorder !== 'undefined'
    );
  }

  protected async start(): Promise<void> {
    this.errorMessage.set(null);
    if (!this.supported) {
      this.errorMessage.set('Audio-Aufnahme wird vom Browser nicht unterstuetzt.');
      return;
    }
    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (error) {
      this.errorMessage.set('Mikrofon-Zugriff verweigert.');
      return;
    }
    const preferredMime = this.pickMimeType();
    this.recorder = preferredMime
      ? new MediaRecorder(this.mediaStream, { mimeType: preferredMime })
      : new MediaRecorder(this.mediaStream);
    this.chunks = [];
    this.recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        this.chunks.push(event.data);
      }
    };
    this.recorder.onstop = () => this.handleRecordingStopped();
    this.recorder.start();
    this.accumulatedMs = 0;
    this.startTimestampMs = Date.now();
    this.elapsedSeconds.set(0);
    this.state.set('recording');
    this.startTimer();
  }

  protected pause(): void {
    if (!this.recorder || this.recorder.state !== 'recording') {
      return;
    }
    this.recorder.pause();
    this.accumulatedMs += this.startTimestampMs ? Date.now() - this.startTimestampMs : 0;
    this.startTimestampMs = null;
    this.stopTimer();
    this.state.set('paused');
  }

  protected resume(): void {
    if (!this.recorder || this.recorder.state !== 'paused') {
      return;
    }
    this.recorder.resume();
    this.startTimestampMs = Date.now();
    this.state.set('recording');
    this.startTimer();
  }

  protected stop(): void {
    if (!this.recorder) {
      return;
    }
    if (this.recorder.state !== 'inactive') {
      this.recorder.stop();
    }
    this.stopTimer();
  }

  protected discard(): void {
    this.cleanupResources();
    this.chunks = [];
    this.state.set('idle');
    this.elapsedSeconds.set(0);
    this.errorMessage.set(null);
    if (this.previewUrl()) {
      URL.revokeObjectURL(this.previewUrl()!);
    }
    this.previewUrl.set(null);
  }

  protected upload(): void {
    const blob = this.collectBlob();
    if (!blob) {
      this.errorMessage.set('Keine Aufnahme vorhanden.');
      return;
    }
    this.state.set('uploading');
    const filename = this.filenameFor(blob);
    this.voiceNoteService.upload(this.slug, blob, this.intent(), filename).subscribe({
      next: (note) => {
        this.voiceNoteSaved.emit(note);
        this.notifications.showMessage('Sprachnotiz hochgeladen. Transkription laeuft im Hintergrund.');
        this.discard();
      },
      error: (response) => {
        this.errorMessage.set(formatHttpError(response, 'Upload fehlgeschlagen.'));
        this.state.set('review');
      },
    });
  }

  protected setIntent(intent: VoiceNoteIntent): void {
    this.intent.set(intent);
  }

  private handleRecordingStopped(): void {
    if (this.startTimestampMs) {
      this.accumulatedMs += Date.now() - this.startTimestampMs;
      this.startTimestampMs = null;
    }
    this.elapsedSeconds.set(Math.round(this.accumulatedMs / 1000));
    const blob = this.collectBlob();
    if (this.previewUrl()) {
      URL.revokeObjectURL(this.previewUrl()!);
    }
    if (blob) {
      this.previewUrl.set(URL.createObjectURL(blob));
    }
    this.releaseStream();
    this.state.set('review');
  }

  private collectBlob(): Blob | null {
    if (!this.chunks.length) {
      return null;
    }
    const type = this.recorder?.mimeType || this.chunks[0].type || 'audio/webm';
    return new Blob(this.chunks, { type });
  }

  private startTimer(): void {
    this.stopTimer();
    this.timerId = window.setInterval(() => {
      const total =
        this.accumulatedMs + (this.startTimestampMs ? Date.now() - this.startTimestampMs : 0);
      this.elapsedSeconds.set(Math.floor(total / 1000));
    }, 250);
  }

  private stopTimer(): void {
    if (this.timerId !== null) {
      window.clearInterval(this.timerId);
      this.timerId = null;
    }
  }

  private releaseStream(): void {
    if (this.mediaStream) {
      for (const track of this.mediaStream.getTracks()) {
        track.stop();
      }
      this.mediaStream = null;
    }
    this.recorder = null;
  }

  private cleanupResources(): void {
    this.stopTimer();
    if (this.recorder && this.recorder.state !== 'inactive') {
      try {
        this.recorder.stop();
      } catch {
        // ignore
      }
    }
    this.releaseStream();
  }

  private pickMimeType(): string | null {
    const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus'];
    for (const candidate of candidates) {
      try {
        if (MediaRecorder.isTypeSupported(candidate)) {
          return candidate;
        }
      } catch {
        // ignore
      }
    }
    return null;
  }

  private filenameFor(blob: Blob): string {
    if (blob.type.includes('ogg')) {
      return 'voice.ogg';
    }
    if (blob.type.includes('mp4')) {
      return 'voice.m4a';
    }
    return 'voice.webm';
  }

  protected formatElapsed(): string {
    const total = this.elapsedSeconds();
    const minutes = Math.floor(total / 60)
      .toString()
      .padStart(2, '0');
    const seconds = (total % 60).toString().padStart(2, '0');
    return `${minutes}:${seconds}`;
  }
}
