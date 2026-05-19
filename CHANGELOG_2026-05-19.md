# Änderungsprotokoll — 2026-05-19

Folge-Session nach dem großen Pre-Demo-Stand vom 2026-05-18.
Schwerpunkt: Spracheingabe (Push-to-Talk) durchgängig, Arbeitstagerfassung mit
KI-Split, und eine projekt-übergreifende Materialmeldungs-Liste.

---

## 1 · Push-to-Talk durchgängig (Issue #4)

### 1.1 Backend `/api/voice/transcribe`
- **Neuer Endpoint** `POST /api/voice/transcribe` (`backend/app/api/voice.py`).
  Multipart Audio rein, JSON raus:
  `{ text_de, original_text, language, translated, provider }`.
- **Neuer Service** `backend/app/services/voice_transcribe.py`:
  1. Whisper transcribe **ohne** `language`-Hint → Auto-Detect.
  2. Wenn erkannte Sprache != `de` → LLM-Call (gpt-4o-mini) übersetzt nach
     Deutsch, bewahrt SHK-Fachvokabular.
  3. Bei fehlendem `OPENAI_API_KEY` antwortet der Endpoint **503** — Frontend
     fällt dann auf Browser-SpeechRecognition zurück.
- **`whisper_provider.py` erweitert:** `language_hint=None` schickt keinen
  `language`-Parameter mehr an OpenAI/faster-whisper — vorher war „de" der
  hartcodierte Default, was bei nicht-deutschen Sprechern bias produziert hätte.
- **Verfügbarkeits-Endpoint** `GET /api/voice/availability` für das Frontend.

### 1.2 Frontend Inline-PTT-Button
- **Neue Komponente** `frontend/src/app/shared/components/ptt-button/`:
  Mic-Button (Toggle), Recording-Animation, Timer, Browser-SpeechRecognition
  als Fallback. Outputs `transcribed` mit `{text, language, translated, source}`.
- **Service** `frontend/src/app/core/services/voice-transcribe.service.ts`:
  `transcribe(blob)` + `isServerAvailable()` (gecached).
- **Globales Utility** `.ptt-field` in `styles.scss`: einheitliches Layout
  Textarea + Mic-Button (Desktop nebeneinander, Mobile gestapelt).
- **Integriert in:** Daily-Report-Form (Schritt 2, 4 Felder),
  Open-Points-Material-Form, Open-Points-Blocker-Form.

---

## 2 · Arbeitstagerfassung mit KI-Split (Issue #3)

### 2.1 DB-Migration `f4a9c2e8b513_daily_report_raw_work_log.py`
- Neue Spalten in `daily_reports`:
  - `raw_work_log TEXT NULL` — Roh-Eingabe des Monteurs (Text oder Voice).
  - `raw_work_log_language VARCHAR(8) NULL` — ISO 639-1 der Voice-Quelle.
- Bestehende `completed_work` / `open_work` bleiben — bei Eingabe via
  Roh-Feld werden sie vom LLM berechnet.

### 2.2 Service `arbeitstagerfassung.py`
- **Ein** LLM-Call (gpt-4o-mini, `response_format=json_object`) macht
  **in einem Hop**:
  1. Übersetzung nach Deutsch (wenn nötig).
  2. Split in `completed` / `pending` (saubere `- `-Stichpunkte).
- Bei LLM-Fehler oder fehlendem Key: Fallback → Roh-Text landet in
  `completed_work`, `pending` leer. Bericht ist nie verloren.

### 2.3 Endpoint-Integration (`backend/app/api/reports.py`)
- **Create:** wenn `raw_work_log` mitkommt → Service splittet →
  `completed_work` + `open_work` werden gefüllt.
- **Update:** Re-Split nur wenn `raw_work_log` im Patch enthalten ist.
  Explizit gesetzte `completed_work`/`open_work` im selben Patch haben Vorrang
  (Edit-Override-Pfad).

### 2.4 Frontend
- **Daily-Report-Form Schritt 2** komplett umgebaut:
  Felder „Erledigte Arbeiten" + „Offene Arbeiten" → ein Feld
  „Arbeitstagerfassung" (großes Textarea + PTT-Button).
- Im Edit-Modus erscheinen die KI-abgeleiteten Felder als „editierbares
  KI-Ergebnis" zum Nachjustieren.
- `canGoNext` akzeptiert sowohl Roh-Feld als auch Legacy-Felder als gültig.
- Sprach-Badge zeigt der Bauleitung, wenn die Quelle nicht-deutsch war
  (z.B. „🌐 Quelle: tr").

### 2.5 Test
```
docker compose exec backend python -c "
from app.services.arbeitstagerfassung import split_arbeitstagerfassung
r = split_arbeitstagerfassung('Bugün üçüncü borunun yalıtımını bitirdik. ...')"
```
liefert:
```
completed: '- Yalıtım des dritten Rohres abgeschlossen'
pending:   '- Montage des vierten Rohres steht noch aus\n- 3 Stück DN50 Bögen fehlen'
detected: tr translated: True
```

---

## 3 · Materialmeldungen-Bündel-Liste (Issue #1)

### 3.1 Push-Notification beim Anlegen
- `push_hooks.py`: neuer Listener `_material_issue_after_insert` → spawnt
  Worker → schickt Push an Lead-Rollen (admin/projektleitung/bauleitung) +
  globale Admins. Titel/Body via neuer `push_messages.material_issue_message`.

### 3.2 Globaler Endpoint
- `GET /api/reports/material-issues/all`:
  - Globale Lead-Rollen (admin/projektleitung) → alle Projekte.
  - Andere → nur Projekte mit Mitgliedschaft.
  - Sortierung: neueste zuerst.

### 3.3 Frontend-Page `/material-issues`
- **Neue Komponente** `frontend/src/app/features/material-issues-all/`:
  - KPI-Cards: Gesamt / Offen / Dringend / Erledigt.
  - Filter: „Erledigte ausblenden" Toggle + Priority-Dropdown.
  - Click auf Zeile toggelt `procurement_status` zwischen `offen` und
    `angekommen` (PATCH `/material-issues/{id}/procurement`).
  - Visuell: durchgestrichener Text + reduzierte Opacity wenn `angekommen`.
  - Dringend-Zeilen mit rotem Border-Left.
- Route `/material-issues` in `app.routes.ts`.
- Action-Cards in allen 4 Role-Landings (Bauleitung/Obermonteur/PL/Monteur).

---

## 4 · Datei-Übersicht

### Neue Files

**Backend:**
- `backend/alembic/versions/f4a9c2e8b513_daily_report_raw_work_log.py`
- `backend/app/api/voice.py`
- `backend/app/services/voice_transcribe.py`
- `backend/app/services/arbeitstagerfassung.py`

**Frontend:**
- `frontend/src/app/shared/components/ptt-button/` (ts/html/scss)
- `frontend/src/app/core/services/voice-transcribe.service.ts`
- `frontend/src/app/features/material-issues-all/` (ts/html/scss)

### Modifizierte Files (heute)

**Backend:**
- `backend/app/main.py` — voice-Router eingebunden
- `backend/app/api/reports.py` — Arbeitstagerfassung-Split + `material-issues/all`-Endpoint
- `backend/app/db/orm_models.py` — `raw_work_log` / `raw_work_log_language`
- `backend/app/models/reports.py` — `raw_work_log` Felder in Pydantic
- `backend/app/services/whisper_provider.py` — `language_hint=None` Auto-Detect
- `backend/app/services/push_hooks.py` — MaterialIssue-Listener
- `backend/app/services/push_messages.py` — `material_issue_message`

**Frontend:**
- `frontend/src/app/app.routes.ts` — Route `/material-issues`
- `frontend/src/styles.scss` — `.ptt-field` Utility
- `frontend/src/app/core/models/report.model.ts` — `raw_work_log` Felder
- `frontend/src/app/core/services/reports.service.ts` — `loadAllMaterialIssues`
- `frontend/src/app/core/services/index.ts` — Export `voice-transcribe.service`
- `frontend/src/app/features/reports/daily-report-form/*` — Arbeitstagerfassung-Step + PTT
- `frontend/src/app/features/open-points/material-form/*` — PTT-Diktat
- `frontend/src/app/features/open-points/blocker-form/*` — PTT-Diktat
- `frontend/src/app/features/role-landing/{bauleitung,obermonteur,monteur,projektleitung}-landing.component.html` — Link auf Material-Issues-Bündel

---

## 5 · Offen / Nicht im Auftrag

- **Live-Audio-Test** im Browser (Whisper-Pipeline mit echter Mikrofon-Aufnahme).
- **Issue #2** (Material-Dropdown statt Freitext): wartet auf die kuratierte
  Artikel-Liste vom User.
- Tests für die neuen Backend-Services (`voice_transcribe`, `arbeitstagerfassung`,
  Push-Hook für MaterialIssue) — derzeit nur manuell verifiziert.
