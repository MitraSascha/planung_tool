import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, of, catchError, map, shareReplay } from 'rxjs';

export interface VoiceTranscribeResult {
  text_de: string;
  original_text: string;
  language: string | null;
  translated: boolean;
  provider: string;
}

/**
 * Schlanker Service für Inline-Push-to-Talk (Mic-Button in jedem Textfeld).
 * Unterschied zu ``VoiceNoteService``: kein Projekt-Slug, keine Persistenz —
 * der Endpoint transkribiert + übersetzt und antwortet sofort.
 */
@Injectable({ providedIn: 'root' })
export class VoiceTranscribeService {
  private readonly http = inject(HttpClient);

  /** Cached, weil sich die Verfügbarkeit zur Laufzeit nicht ändert. */
  private availability$?: Observable<boolean>;

  /** Audio-Blob → deutscher Text. Filename robust setzen, sonst lehnt
   *  Whisper den Stream ab. */
  transcribe(audioBlob: Blob, filename = 'voice.webm'): Observable<VoiceTranscribeResult> {
    const fd = new FormData();
    fd.append('file', audioBlob, filename);
    fd.append('target_language', 'de');
    return this.http.post<VoiceTranscribeResult>('/api/voice/transcribe', fd);
  }

  /** Frontend prüft einmal, ob der Server-Endpoint aktiv ist. Wenn nicht
   *  (Key fehlt), wird der Browser-SpeechRecognition-Fallback verwendet. */
  isServerAvailable(): Observable<boolean> {
    if (!this.availability$) {
      this.availability$ = this.http
        .get<{ available: boolean }>('/api/voice/availability')
        .pipe(
          map((r) => !!r.available),
          catchError(() => of(false)),
          shareReplay(1),
        );
    }
    return this.availability$;
  }
}
