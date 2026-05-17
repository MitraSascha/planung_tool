export type VoiceNoteIntent = 'daily_report' | 'ibn' | 'uebergabe' | 'freitext';

export type VoiceNoteTranscriptionStatus = 'pending' | 'ok' | 'failed';

export interface VoiceNoteRead {
  id: number;
  project_slug: string;
  user_id: number | null;
  username: string | null;
  audio_url: string;
  content_type: string | null;
  duration_seconds: number | null;
  intent: VoiceNoteIntent;
  transcript: string | null;
  transcript_provider: string | null;
  transcript_language: string | null;
  transcription_status: VoiceNoteTranscriptionStatus;
  transcription_error: string | null;
  created_at: string;
  transcribed_at: string | null;
}

export interface VoiceNoteUpdate {
  transcript?: string | null;
  intent?: VoiceNoteIntent;
}

export const VOICE_NOTE_INTENT_LABELS: Record<VoiceNoteIntent, string> = {
  daily_report: 'Tagesbericht',
  ibn: 'Inbetriebnahme',
  uebergabe: 'Uebergabe',
  freitext: 'Freitext',
};
