# Tagesbericht: „Arbeitstagerfassung" — KI splittet Erledigt+Offen aus einem Feld

**Status:** DONE — 2026-05-19 implementiert
**Erstellt:** 2026-05-19
**Folge-Erweiterung:** Material-Extraktion aus dem Roh-Text — siehe
[[2026-05-19_tagesbericht_material_dropdown]] (Entscheidung 2026-05-19).
**Bereich:** Daily-Report-Form / KI-Integration

## Anforderung

Aktuell hat der Tagesbericht **zwei getrennte Felder** für „Erledigte Arbeiten" und „Offene Arbeiten". Soll zu **einem einzigen Feld** zusammengefasst werden, das **„Arbeitstagerfassung"** heißt.

- User gibt Freitext ein (oder Push-to-Talk, siehe [[2026-05-19_push_to_talk_whisper]]) — beschreibt **was er gemacht hat** und **was offen geblieben ist** in einem Rutsch.
- **KI** analysiert den Text und teilt ihn intern auf in:
  - `completed_work` — sauber formatierte „Erledigte Aufgaben"
  - `pending_work` — sauber formatierte „Offene Aufgaben"
- **User sieht nur das eine Feld** — die KI-Aufteilung passiert im Hintergrund (oder als „Vorschau vor dem Absenden", offen).

## Warum

Spart dem Monteur den Kopf-Aufwand zu trennen — er denkt einfach laut über den Tag, die KI strukturiert.

## Implementierungs-Skizze

- Frontend: Feld „Erledigte Arbeiten" + „Offene Arbeiten" → ein Feld „Arbeitstagerfassung" (großes Textarea, Push-to-Talk-Button).
- Backend: Beim POST des Tagesberichts wird der Roh-Text per LLM-Call (Claude/Codex schon im Stack) analysiert. Prompt liefert JSON `{"completed": "...", "pending": "..."}`.
- Persistenz: Roh-Text speichern (z.B. neue Spalte `daily_reports.raw_work_log`), zusätzlich die zwei abgeleiteten Felder befüllen.
- Idempotenz: Wenn ein bestehender Bericht editiert wird, soll der Roh-Text die Quelle bleiben — beim Re-Submit neu splitten.
- **Mehrsprachigkeit:** Wenn der Roh-Text nicht-Deutsch ist (siehe Whisper-Pipeline in [[2026-05-19_push_to_talk_whisper]]), übersetzt der LLM im **selben Prompt** nach Deutsch + macht den Erledigt/Offen-Split — ein Call, kein zweiter Hop.

## Offene Fragen

- Welches Modell? (Wahrscheinlich Claude Haiku 4.5 — schnell, billig, deutsch gut)
- Soll der Monteur die KI-Aufteilung im UI sehen und korrigieren können, oder läuft sie unsichtbar?
- Was passiert wenn der LLM-Call scheitert? (Fallback: kompletter Text landet in „completed", `pending` bleibt leer + Warn-Hinweis)

## Verwandte Bestandteile

- `frontend/src/app/features/reports/daily-report-form/daily-report-form.component.ts`
- `backend/app/api/reports.py` (DailyReport-Create/Update)
- LLM-Anbindung: schon vorhanden via Codex/Claude-Code-CLI in `backend/app/services/`
