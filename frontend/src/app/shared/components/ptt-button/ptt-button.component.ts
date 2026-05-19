import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  OnDestroy,
  Output,
  inject,
  input,
  signal,
} from '@angular/core';

import { NotificationService } from '../../../core/services/notification.service';
import {
  VoiceTranscribeResult,
  VoiceTranscribeService,
} from '../../../core/services/voice-transcribe.service';

type PttState = 'idle' | 'recording' | 'transcribing' | 'error';

export interface PttTranscriptionEvent {
  /** Deutscher Text — soll ins Eingabefeld. */
  text: string;
  /** Erkannte Quellsprache (ISO 639-1) — null wenn nicht erkennbar. */
  language: string | null;
  /** True wenn der LLM den Text vom Quellsprache nach Deutsch übersetzt hat. */
  translated: boolean;
  /** Wo das Transkript herkam: 'server' = Whisper-Pipeline, 'browser' = SpeechRecognition-Fallback. */
  source: 'server' | 'browser';
}

/**
 * Inline-Push-to-Talk-Button.
 *
 * UX:
 *   - Klick startet/stoppt die Aufnahme (Toggle, kein Hold — robuster auf Mobile).
 *   - Während der Aufnahme blinkt der Button rot + zeigt verstrichene Zeit.
 *   - Stop → POST an /api/voice/transcribe → emittiert ``transcribed`` mit
 *     dem deutschen Text. Eltern-Komponente fügt den Text ins Feld ein.
 *   - Fallback: wenn Server-Endpoint nicht verfügbar oder fehlschlägt, nutzt
 *     der Button die Browser-eigene SpeechRecognition (kein Übersetzungs-Hop —
 *     Browser transkribiert in der Lokal-Sprache, default ``de-DE``).
 *
 * Verwendung:
 *   ```html
 *   <textarea [(ngModel)]="text"></textarea>
 *   <app-ptt-button (transcribed)="onTranscribed($event)"></app-ptt-button>
 *   ```
 */
@Component({
  selector: 'app-ptt-button',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './ptt-button.component.html',
  styleUrl: './ptt-button.component.scss',
})
export class PttButtonComponent implements OnDestroy {
  private readonly transcribeSvc = inject(VoiceTranscribeService);
  private readonly notifications = inject(NotificationService);

  /** Kompakte Variante (nur Icon, kein Label) — für inline neben einem Eingabefeld. */
  readonly compact = input<boolean>(false);
  /** Tooltip / Aria-Label. */
  readonly label = input<string>('Diktieren');

  @Output() readonly transcribed = new EventEmitter<PttTranscriptionEvent>();

  protected readonly state = signal<PttState>('idle');
  protected readonly elapsedSeconds = signal(0);
  protected readonly errorMessage = signal<string | null>(null);

  private recorder: MediaRecorder | null = null;
  private mediaStream: MediaStream | null = null;
  private chunks: Blob[] = [];
  private timerId: number | null = null;
  private startTimestampMs: number | null = null;

  // Browser-Fallback (SpeechRecognition)
  private speechRecognition: any = null;
  private serverAvailable: boolean | null = null;

  ngOnDestroy(): void {
    this.cleanup();
  }

  protected get hasMediaRecorder(): boolean {
    return (
      typeof navigator !== 'undefined' &&
      !!navigator.mediaDevices &&
      typeof MediaRecorder !== 'undefined'
    );
  }

  protected get hasBrowserSpeechRecognition(): boolean {
    return (
      typeof window !== 'undefined' &&
      (!!(window as any).SpeechRecognition || !!(window as any).webkitSpeechRecognition)
    );
  }

  protected async onClick(): Promise<void> {
    this.errorMessage.set(null);
    if (this.state() === 'recording') {
      this.stopRecording();
      return;
    }
    if (this.state() !== 'idle') {
      return;
    }
    // Verfügbarkeit nur einmal prüfen, dann gemerkt.
    if (this.serverAvailable === null) {
      this.serverAvailable = await new Promise<boolean>((resolve) => {
        this.transcribeSvc.isServerAvailable().subscribe({
          next: (v) => resolve(v),
          error: () => resolve(false),
        });
      });
    }
    if (this.serverAvailable && this.hasMediaRecorder) {
      await this.startServerRecording();
    } else if (this.hasBrowserSpeechRecognition) {
      this.startBrowserRecognition();
    } else {
      this.setError('Spracheingabe wird vom Browser nicht unterstützt.');
    }
  }

  // ─── Server-Pfad (Whisper) ────────────────────────────────────────────────

  private async startServerRecording(): Promise<void> {
    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      this.setError('Mikrofon-Zugriff verweigert.');
      return;
    }
    const mime = this.pickMimeType();
    this.recorder = mime
      ? new MediaRecorder(this.mediaStream, { mimeType: mime })
      : new MediaRecorder(this.mediaStream);
    this.chunks = [];
    this.recorder.ondataavailable = (ev) => {
      if (ev.data && ev.data.size > 0) this.chunks.push(ev.data);
    };
    this.recorder.onstop = () => this.handleServerStop();
    this.recorder.start();
    this.startTimestampMs = Date.now();
    this.elapsedSeconds.set(0);
    this.state.set('recording');
    this.startTimer();
  }

  private stopRecording(): void {
    this.stopTimer();
    if (this.recorder && this.recorder.state !== 'inactive') {
      try {
        this.recorder.stop();
      } catch {
        // Wenn stop wirft: trotzdem Stream freigeben und Idle gehen.
        this.releaseStream();
        this.state.set('idle');
      }
    } else if (this.speechRecognition) {
      // Browser-Fallback: stop() löst onresult → onend aus.
      try {
        this.speechRecognition.stop();
      } catch {
        // ignore
      }
    }
  }

  private handleServerStop(): void {
    this.releaseStream();
    if (!this.chunks.length) {
      this.state.set('idle');
      return;
    }
    const type = this.recorder?.mimeType || this.chunks[0].type || 'audio/webm';
    const blob = new Blob(this.chunks, { type });
    const filename = this.filenameFor(blob);
    this.state.set('transcribing');
    this.transcribeSvc.transcribe(blob, filename).subscribe({
      next: (res: VoiceTranscribeResult) => {
        const text = (res.text_de || '').trim();
        if (!text) {
          this.setError('Keine Sprache erkannt — bitte erneut probieren.');
          return;
        }
        this.transcribed.emit({
          text,
          language: res.language,
          translated: res.translated,
          source: 'server',
        });
        if (res.translated) {
          this.notifications.showMessage(
            `🌐 Aus dem ${this.prettyLanguageName(res.language)} ins Deutsche übersetzt.`,
          );
        }
        this.state.set('idle');
        this.elapsedSeconds.set(0);
      },
      error: (err) => {
        // Server-Pfad versagt → Browser-Fallback wenn möglich.
        if (this.hasBrowserSpeechRecognition) {
          this.notifications.showMessage(
            'Server-Transkription fehlgeschlagen — nutze Browser-Spracherkennung.',
          );
          this.serverAvailable = false;
          this.state.set('idle');
          // Direkt nochmal triggern wäre ungewohnt — User klickt nochmal.
        } else {
          this.setError('Transkription fehlgeschlagen: ' + (err?.message || 'unbekannter Fehler'));
        }
      },
    });
  }

  // ─── Browser-Pfad (SpeechRecognition-Fallback) ────────────────────────────

  private startBrowserRecognition(): void {
    const SR =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) {
      this.setError('Spracheingabe nicht unterstützt.');
      return;
    }
    const rec = new SR();
    rec.lang = 'de-DE';
    rec.continuous = false;
    rec.interimResults = false;
    rec.onstart = () => {
      this.startTimestampMs = Date.now();
      this.elapsedSeconds.set(0);
      this.state.set('recording');
      this.startTimer();
    };
    rec.onresult = (event: any) => {
      const text = (event?.results?.[0]?.[0]?.transcript || '').trim();
      if (text) {
        this.transcribed.emit({
          text,
          language: 'de',
          translated: false,
          source: 'browser',
        });
      } else {
        this.setError('Keine Sprache erkannt — bitte erneut probieren.');
      }
    };
    rec.onerror = (event: any) => {
      const code = event?.error || 'unknown';
      if (code === 'no-speech') {
        this.setError('Keine Sprache erkannt.');
      } else if (code === 'not-allowed') {
        this.setError('Mikrofon-Zugriff verweigert.');
      } else {
        this.setError('Spracherkennung fehlgeschlagen (' + code + ').');
      }
    };
    rec.onend = () => {
      this.stopTimer();
      if (this.state() === 'recording') {
        this.state.set('idle');
      }
      this.speechRecognition = null;
    };
    this.speechRecognition = rec;
    try {
      rec.start();
    } catch (err) {
      this.setError('Spracherkennung konnte nicht starten.');
    }
  }

  // ─── Helpers ──────────────────────────────────────────────────────────────

  private setError(msg: string): void {
    this.errorMessage.set(msg);
    this.state.set('error');
    this.releaseStream();
    this.stopTimer();
    setTimeout(() => {
      if (this.state() === 'error') {
        this.state.set('idle');
        this.errorMessage.set(null);
      }
    }, 3500);
  }

  private releaseStream(): void {
    if (this.mediaStream) {
      for (const t of this.mediaStream.getTracks()) t.stop();
      this.mediaStream = null;
    }
    this.recorder = null;
  }

  private startTimer(): void {
    this.stopTimer();
    this.timerId = window.setInterval(() => {
      const start = this.startTimestampMs ?? Date.now();
      this.elapsedSeconds.set(Math.floor((Date.now() - start) / 1000));
    }, 250);
  }

  private stopTimer(): void {
    if (this.timerId !== null) {
      window.clearInterval(this.timerId);
      this.timerId = null;
    }
  }

  private pickMimeType(): string | null {
    const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
    for (const c of candidates) {
      try {
        if (MediaRecorder.isTypeSupported(c)) return c;
      } catch {
        // ignore
      }
    }
    return null;
  }

  private filenameFor(blob: Blob): string {
    if (blob.type.includes('ogg')) return 'voice.ogg';
    if (blob.type.includes('mp4')) return 'voice.m4a';
    return 'voice.webm';
  }

  private prettyLanguageName(code: string | null): string {
    if (!code) return 'Original';
    const map: Record<string, string> = {
      tr: 'Türkischen',
      ru: 'Russischen',
      pl: 'Polnischen',
      ku: 'Kurdischen',
      ar: 'Arabischen',
      en: 'Englischen',
      it: 'Italienischen',
      es: 'Spanischen',
      ro: 'Rumänischen',
      bg: 'Bulgarischen',
      sr: 'Serbischen',
      uk: 'Ukrainischen',
    };
    return map[code.toLowerCase()] || code;
  }

  protected formatElapsed(): string {
    const t = this.elapsedSeconds();
    const m = Math.floor(t / 60).toString().padStart(2, '0');
    const s = (t % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  }

  private cleanup(): void {
    this.stopTimer();
    if (this.recorder && this.recorder.state !== 'inactive') {
      try {
        this.recorder.stop();
      } catch {
        // ignore
      }
    }
    if (this.speechRecognition) {
      try {
        this.speechRecognition.stop();
      } catch {
        // ignore
      }
      this.speechRecognition = null;
    }
    this.releaseStream();
  }
}
