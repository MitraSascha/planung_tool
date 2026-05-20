# Tagesbericht: Push-to-Talk via OpenAI Whisper (+ Fallback Browser-Voice)

**Status:** DONE — 2026-05-19 implementiert
**Erstellt:** 2026-05-19
**Bereich:** Daily-Report-Form / Voice-Input

## Anforderung

In jedes größere Text-Eingabefeld (primär „Arbeitstagerfassung", siehe [[2026-05-19_arbeitstagerfassung_ki_split]]) einen **Push-to-Talk-Button** einbauen:

1. **Primär:** OpenAI Whisper (Audio → Transkription).
2. **Fallback:** Browser-natives `webkitSpeechRecognition` / `SpeechRecognition` (wenn Whisper-Key fehlt oder Netzwerk-Call scheitert).

User-Quote: „Push to Talk einbauen OpenAI-Whisper. key gebe ich dir wenn es so weit ist. Als Fallback das Standard Internet Voice"

## Implementierungs-Skizze

- **Frontend:** Push-to-Talk-Button-Komponente (gehört in das Eingabefeld, siehe analog MitraApp-Pattern aus dem Memory). Aufnahme via `MediaRecorder`, Stop → POST an Backend.
- **Backend:** Neuer Endpoint `POST /api/voice/transcribe` (multipart audio) → ruft OpenAI Whisper API. Key aus ENV `OPENAI_API_KEY`.
- **Fallback-Logik:** Frontend probiert zuerst Server-Endpoint. Wenn 503 (kein Key) oder Netzwerkfehler → fallback auf Browser-API.
- **Resultat:** Transkribierter Text wird ins Textfeld eingefügt (an Cursor-Position oder appended).

## Mehrsprachigkeit (entschieden 2026-05-19)

Team ist international (Türkisch, Russisch, Kurdisch, etc. möglich). Anforderung: Monteur spricht in seiner Muttersprache, Bericht landet auf Deutsch.

**Methode:** Zwei-Schritt-Pipeline im Backend
1. **Whisper transcribe** mit Sprach-Auto-Detect → Roh-Transkript + erkannte Sprache (`language` aus der Whisper-Response).
2. **Wenn `language != "de"`** → LLM-Call (vorhandener Claude/Codex-Stack) übersetzt nach Deutsch, behält SHK-Fachvokabular bei.
3. Response liefert `{ text_de: "...", original_text: "...", language: "tr", translated: true|false }` — Frontend füllt das Feld mit `text_de`.

**NICHT** Whisper-`translate`-Modus verwenden (übersetzt nur nach Englisch, nicht Deutsch).

**Synergie mit [[2026-05-19_arbeitstagerfassung_ki_split]]:** Der Arbeitstagerfassung-Pipeline läuft eh durch ein LLM für den Erledigt/Offen-Split — Übersetzung kann im selben Prompt erledigt werden, kein zusätzlicher Call nötig. Für andere Push-to-Talk-Felder (Mängelnotiz etc.) ist ein separater Mini-Übersetzungs-Call OK.

## Bestehende Infrastruktur (schon im Repo, nutzbar)

- `backend/app/services/whisper_provider.py` — Provider-Abstraktion (openai / local / chain / codex). `OPENAI_API_KEY` jetzt gesetzt.
- `backend/app/services/whisper_pipeline.py` — Event-Listener
- Settings: `whisper_provider=openai`, `whisper_model=small`, Fallback-Chain konfigurierbar via `WHISPER_CHAIN`
- Frontend: `VoiceRecorderComponent` + `VoiceNoteService` (bisher nur als eigenständiges Voice-Notes-Feature) — kann als Basis für Inline-Push-to-Talk wiederverwendet werden.

## Offene Punkte

- Neue, leichtere Push-to-Talk-Komponente für Inline-Verwendung in Eingabefeldern (Mic-Button neben/in Textarea, kein Notiz-Workflow)
- Soll der Push-to-Talk-Button auch in andere Felder (Mängelnotiz, Materialmeldung-Notiz etc.) — oder erstmal nur in Arbeitstagerfassung?

## Verwandte Bestandteile

- `frontend/src/app/shared/components/voice-recorder/` — existiert bereits, evtl. wiederverwenden/erweitern
- `frontend/src/app/features/voice-notes/` — existiert, evtl. Service-Layer dort
