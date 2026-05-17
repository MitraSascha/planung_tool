import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { VoiceNoteIntent, VoiceNoteRead, VoiceNoteUpdate } from '../models/voice-note.model';

@Injectable({ providedIn: 'root' })
export class VoiceNoteService {
  private readonly http = inject(HttpClient);

  list(slug: string): Observable<VoiceNoteRead[]> {
    return this.http.get<VoiceNoteRead[]>(`/api/projects/${slug}/voice-notes`);
  }

  upload(slug: string, audioBlob: Blob, intent: VoiceNoteIntent, filename = 'voice.webm'): Observable<VoiceNoteRead> {
    const formData = new FormData();
    formData.append('file', audioBlob, filename);
    formData.append('intent', intent);
    return this.http.post<VoiceNoteRead>(`/api/projects/${slug}/voice-notes`, formData);
  }

  update(slug: string, id: number, patch: VoiceNoteUpdate): Observable<VoiceNoteRead> {
    return this.http.patch<VoiceNoteRead>(`/api/projects/${slug}/voice-notes/${id}`, patch);
  }

  delete(slug: string, id: number): Observable<void> {
    return this.http.delete<void>(`/api/projects/${slug}/voice-notes/${id}`);
  }

  /** Liest die aktuelle VoiceNote — geeignet fuer Polling bei status="pending". */
  pollStatus(slug: string, id: number): Observable<VoiceNoteRead> {
    return this.http.get<VoiceNoteRead>(`/api/projects/${slug}/voice-notes/${id}`);
  }
}
