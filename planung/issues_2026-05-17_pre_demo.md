# Pre-Demo Issues — 2026-05-17

Befund aus Code-Audit am 17.05. vor der morgigen Vorstellung der 3 Rollen
(Monteur, Obermonteur, Projektleitung).
Priorität: **P1** = Demo-Killer / **P2** = peinlich, fixbar / **P3** = Tech-Debt, nicht heute.

---

## P1 — heute zwingend

### #0a [P1] Checklisten persistieren nur in localStorage
- **Symptom:** `OBERMONTEUR_Checklisten.html` (und ähnliche Listen in
  Monteur-/Bauleitung-Docs) nutzt nackte `<input type="checkbox">` ohne
  `data-field-id`. Das injizierte form-sync-snippet greift NICHT, Daten
  liegen nur im localStorage des Browsers. Audit-Lücke, Geräte-Wechsel
  vernichtet alle Häkchen.
- **Fix:**
  1. Template `checklisten` (e2f5b8a1c907_seed_remaining_templates.py:[suchen])
     anpassen: jede Checkbox bekommt `data-field-id="obermonteur.checklisten.<section>.<itemSlug>"`.
  2. Gleichbehandlung in `template_renderer.py` für alle Checklist-Templates
     (auch monteur-tagescheckliste).
  3. Existierendes `form_responses`-System nimmt die POSTs schon
     entgegen (`PUT /api/projects/{slug}/form-responses/{doc_path}`).
- **Akzeptanz:** Abhaken in Browser A → erscheint in Browser B beim
  Reload. `form_responses`-Tabelle hat Rows mit `value_bool`.

### #0b [P1] Cross-Document-Auto-Sync bei Domain-Änderungen
- **Symptom:** Wenn Daten aktualisiert werden (Pumpendaten in
  `HeatingDesign`, Material in `MaterialItem`, Termine in
  `section_schedules`, Risiko in `RiskIssue`), bleibt die alte
  HTML-Datei in `storage/projects/<slug>/...` unverändert bis jemand
  manuell "Dokumente neu generieren" klickt. Eine Pumpen-Daten-Änderung
  in der Hydraulik-Doc taucht NICHT automatisch im Inbetriebnahme-
  Protokoll oder Material-Werkzeug-Doc auf.
- **Architektur-Optionen:**
  1. **Live-Render** (sauberste Lösung): `GET /api/projects/{slug}/outputs/file/<path>`
     löst beim Zugriff `render_template_for_project()` aus statt die
     statische Datei zu lesen. Storage-File entfällt für gerenderte
     Templates. Nachteil: jeder Klick = Render-Latenz.
  2. **Event-driven Re-Render**: SQLAlchemy event listeners auf die
     Domain-Tabellen (`HeatingDesign`, `HeatingCircuit`, `MaterialItem`,
     `RiskIssue`, `SectionSchedule`, `TeamStatusEntry`,
     `ProjectSection`) triggern bei Insert/Update/Delete einen
     Re-Render der **betroffenen** Templates über `template_publisher`.
     Asynchron, kein UI-Block.
  3. **Lazy stale-marker**: Domain-Change setzt einen Flag pro
     Template; nächster `GET outputs/file/...` sieht Flag → rendert
     dieses eine Template neu und überschreibt die Datei.
- **Empfehlung:** Option 2 für DB-getriebene Domains, Option 1 für
  form_responses-getriebene Felder (die sind eh personenbezogen und
  per-User aggregiert).
- **Demo-Workaround heute:** Vor der Demo einmal "Dokumente neu generieren"
  ausführen lassen. Falls live etwas geändert wird, denselben Knopf
  vor dem nächsten Klick nochmal drücken.
- **Akzeptanz (echter Fix, ggf. nicht heute):** Pumpenwert in
  HeatingDesign ändern → ohne weitere Aktion zeigt das
  Inbetriebnahmeprotokoll und das Material-Werkzeug-Doc den neuen Wert.

### #1 [P1] Frontend-Container möglicherweise mit altem Code
- **Symptom:** Container `hez-640-frontend` gebaut 2026-05-17 15:25 lokal.
  Seitdem sind diverse `.ts`-Files geändert (app.ts, app.routes.ts,
  app.config.ts, mehrere services/models). Browser zeigt evtl. alten Bundle.
- **Fix:**
  ```
  docker compose build frontend && docker compose up -d frontend
  ```
  Danach in Inkognito-Tab `http://localhost/` öffnen und das Verhalten der
  drei Rollen einmal durchklicken.
- **Akzeptanz:** alle seit 15:25 geänderten Frontend-Features funktionieren
  im laufenden Container.

### #2 [P1] Datenmodell-Spaltung — Monteur-Meldungen erscheinen nicht im PL-Template
- **Befund:**
  - `MaterialIssue` (orm_models.py:215) ≠ `MaterialItem` (orm_models.py:647)
  - `Blocker`       (orm_models.py:231) ≠ `RiskIssue`    (orm_models.py:676)
  - `template_renderer.py:735` rendert `material_items` nur aus **MaterialItem**.
  - `template_renderer.py:756` rendert `risk_issues`   nur aus **RiskIssue**.
- **Folge:** Was der Monteur per Tagesbericht / Material-Form / Blocker-Form
  meldet, taucht in den Projektleitung-Templates "Material & Werkzeug" und
  "Risiken & Mängel" **nicht** auf.
- **Demo-Workaround (heute, klein):** Vor der Demo manuell ein paar
  MaterialItem- und RiskIssue-Einträge für `hez-640` anlegen, damit die
  Templates etwas zeigen:
  ```
  curl -X POST http://localhost:8000/api/projects/hez-640/material-items \
       -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
       -d '{"name":"Stahlrohre DN50","kind":"material","soll_qty":40,"unit":"m","status":"bestellt"}'
  curl -X POST http://localhost:8000/api/projects/hez-640/risk-issues \
       -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
       -d '{"description":"Wohnung nicht zugänglich","kind":"risiko","severity":"hoch","due_date":"2026-06-01"}'
  ```
- **Akzeptanz für Demo:** Im PL-Template steht mindestens 1 Material-Zeile
  und 1 Risiko-Zeile.
- **Echter Fix (nicht heute):** Entscheidung treffen — entweder die zwei
  Welten zusammenführen, oder im Renderer auch `MaterialIssue` /
  `Blocker` einbeziehen.

### #3 [P1] Open-Points-Komponente zeigt keine Liste, kein Edit
- **Datei:** `frontend/src/app/features/open-points/open-points.component.ts`
- **Befund:** Komponente lädt nur `reports.loadSummary(slug)` und zeigt
  Zahlen. Backend liefert seit längerem
  `GET  /api/reports/projects/{slug}/material-issues`,
  `GET  /api/reports/projects/{slug}/blockers`,
  `PATCH .../{id}` (Status setzen), die Komponente nutzt sie nicht.
- **Demo-Workaround:** Open-Points-Tab in der Demo überspringen oder
  vorwarnen ("Liste/Edit kommt in der nächsten Iteration").
- **Echter Fix (heute machbar in ~1–2 h):**
  1. `reports.service.ts` um `listMaterialIssues(slug)` und `listBlockers(slug)`
     ergänzen.
  2. Komponente abhängig vom `activeTab` Signal die jeweilige Liste laden.
  3. Pro Zeile ein Status-Dropdown, das `PATCH .../{id}` aufruft.
- **Akzeptanz:** Tab "Material" zeigt offene Materialmeldungen, Tab "Blocker"
  zeigt offene Blocker. Status pro Eintrag änderbar.

---

## P2 — heute wünschenswert

### #4 [P2] Tagesbericht erzeugt stille Duplikate
- **Datei:** `backend/app/api/reports.py:161-180`
- **Befund:** Wenn der Monteur im Tagesbericht `material_missing` oder
  `blockers` ausfüllt, wird **zusätzlich** automatisch ein `MaterialIssue`-
  bzw. `Blocker`-Eintrag erstellt — ohne FK zum verursachenden
  Tagesbericht. Wenn der Monteur dieselbe Sache hinterher noch über die
  Material-/Blocker-Form meldet, gibt's zwei Einträge ohne Querverweis.
- **Fix-Optionen:**
  - **Option A (schnell, heute):** Auto-Anlage ausbauen. Nur Daily-Report
    speichern, separates Melden über die Forms überlassen.
  - **Option B (sauber):** `daily_report_id`-FK an `MaterialIssue` / `Blocker`
    hängen + Migration + Dedupe-Logik.
- **Empfehlung:** Heute Option A — die UI hat keine Bestätigung "Auto-Issue
  angelegt", also bemerkt der User die Duplikate jetzt schon nicht.
- **Akzeptanz:** Daily-Report-POST erzeugt nur den Daily-Report, sonst nichts.

### #5 [P2] Logo-Platzhalter im Renderer
- **Datei:** `backend/app/services/template_renderer.py:327, 354`
- **Befund:** Zwei `<!-- TODO: Logo-Asset einsetzen -->`-Markierungen.
  Die generierten Dokumente/PDFs zeigen die Mitra-Brandbar ohne Logo.
  Kunde fragt im Demo danach.
- **Fix:** Wenn Logo-Datei vorhanden: nach `frontend/public/` oder
  `storage/static/` legen und im Renderer als `<img>` einsetzen.
  Sonst: Demo-Vorbereitung — Brandbar dezent reduzieren ("MITRA"-Wortmarke
  als Text, statt leerem Platzhalter).
- **Akzeptanz:** Kein "TODO: Logo"-Kommentar mehr im Output.

### #6 [P2] Doppelter Blocker-Endpoint mit inkonsistenter Validierung
- **Dateien:**
  - `backend/app/api/reports.py:316` — `POST /api/reports/projects/{slug}/blockers` mit `BlockerCreate` (description min_length=1, severity strict pattern)
  - `backend/app/api/domains.py:307` — `POST /api/projects/{slug}/blockers`         mit `BlockerIn`     (description ohne min_length, severity ohne pattern)
- **Befund:** Beide Endpoints schreiben in dieselbe `blockers`-Tabelle.
  domains.py akzeptiert leere Description und Quatsch-Severity. Wer welchen
  Endpoint nutzt, hängt nur am UI-Pfad.
- **Fix (heute, klein):** Entweder
  - `domains.py:307` `BlockerIn` auf die Validatoren von `BlockerCreate`
    angleichen, ODER
  - `POST /{slug}/blockers` in domains.py entfernen, alle Schreibvorgänge
    durch reports.py.
- **Akzeptanz:** Es gibt nur einen schreibenden Pfad ODER beide
  validieren identisch.

### #7 [P2] Auth-Token landet in Nginx-Logs (file-download)
- **Datei:** `backend/app/api/projects.py:693,714`
- **Befund:** `get_current_user_query_or_header` akzeptiert
  `?token=eyJ...` für `<a href>`-Download und PDF-Embed. Nginx loggt das
  vollständig (siehe `docker logs hez-640-nginx-1`). `JWT_ACCESS_TOKEN_MINUTES=480`
  (8h) — wer einmal Logs sieht, hat 8h gültige Sessions in der Hand.
- **Fix-Optionen:**
  - **Heute klein:** `JWT_ACCESS_TOKEN_MINUTES` in `.env` auf 60 setzen +
    Stack neu starten. Reduziert das Window.
  - **Echter Fix:** Separate kurzlebige Download-Tokens (5–10 min), via
    `POST /api/projects/{slug}/download-token` ausgestellt, NUR für genau
    diesen einen Pfad gültig.
- **Akzeptanz heute:** Token-Lebensdauer ≤ 60 Minuten.

---

## P3 — nicht heute, in den Backlog

### #8 [P3] `MaterialItem` und `RiskIssue` ohne `user_id`
- **Datei:** `backend/app/db/orm_models.py:647, 676`
- **Befund:** Während `MaterialIssue` und `Blocker` ein `user_id`-FK haben,
  haben `MaterialItem` und `RiskIssue` keinen. Man kann nicht nachvollziehen,
  wer einen Inventar- oder Risiko-Eintrag angelegt hat.
- **Fix:** Migration `add user_id to material_items + risk_issues` mit
  `nullable=True` (Bestand bleibt erhalten), neue Einträge mit
  `current_user.id`.

### #9 [P3] Drei Router teilen `/api/projects/`
- **Datei:** `backend/app/main.py:45,46,57`
- **Befund:** `projects_router`, `form_responses_router` und `domains_router`
  hängen alle unter `/api/projects`. Heute kollisionsfrei, aber jede neue
  `@router.get("/{slug}/...")` in einem der drei kann eine Route im anderen
  shadowen — die Include-Reihenfolge entscheidet stillschweigend.
- **Fix:** Klare Sub-Prefixes (z.B. `/api/projects/{slug}/forms`,
  `/api/projects/{slug}/domains`) — größerer Refactor, FE muss mit.

### #10 [P3] FastAPI `@app.on_event("startup")` deprecated
- **Datei:** `backend/app/main.py:31`
- **Befund:** Deprecated seit FastAPI 0.93 (2023). DeprecationWarning beim
  Start, funktioniert.
- **Fix:** Migration zu `lifespan`-Context-Manager (~15 Zeilen).

---

## Test-Plan vor der Demo

Nach den P1-Fixes (mindestens #1 und Workaround #2):

1. `docker compose ps` — alle Services healthy.
2. Login als **Murat** (monteur) → Tagesbericht ausfüllen, Material-Form
   ausfüllen, Blocker-Form ausfüllen, alles Speichern.
3. Login als **Rojhat** (obermonteur) → Wochenbericht, sieht Monteur-Berichte.
4. Login als **Patrick** (projektleitung) → "Dokumente neu generieren"
   klicken → PL-Dokumente öffnen, prüfen ob Material/Risiken-Templates etwas
   zeigen.
5. Kein PII-Token `[[PII:...]]` mehr im Übergabeprotokoll-HTML.
6. Browser-Tab schließen, Inkognito öffnen, neu einloggen — Workflow läuft.
