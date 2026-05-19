# Änderungsprotokoll — 2026-05-18

Komplette Session-Doku aller Backend-/Frontend-/DB-Änderungen.

---

## 1 · Infrastruktur & Bugfixes (Start der Session)

### 1.1 Storage-Permissions
- **Problem:** `POST /api/projects` → 500. Backend-Container läuft als `appuser` (uid 1000), `storage/` gehörte `root:root` → `PermissionError` beim `mkdir` von `workspaces/<slug>/`.
- **Fix:** `chown -R 1000:1000 storage/`
- **Hinweis:** Dockerfile macht `chown` beim Build, Bind-Mount überschreibt das. Bei neuem Deploy gleiches chown wieder nötig — sollte ins README oder per init-Container automatisiert werden.

### 1.2 Verwaister DB-Eintrag bei mkdir-Fehler
- **Datei:** `backend/app/api/projects.py:443-497` (`create_project`)
- **Problem:** `db.commit()` lief **vor** `create_project_workspace()`. Bei mkdir-Fehler blieb DB-Eintrag (Projekt `hez-640` als „draft") ohne Workspace zurück.
- **Fix:** Workspace-Erstellung **vor** Commit, mit `OSError`-Rollback → keine verwaisten Einträge mehr.

### 1.3 Cleanup
- Geister-Projekt `hez-640` (Draft ohne Workspace) gelöscht.
- 7 Mitglieder von `hez-640` zu `hez640` migriert (waren auf das falsche Projekt geklickt worden).
- Später kompletter DB-Cleanup vor neuem Start (`DELETE FROM projects`, alle abhängigen Tabellen via Cascade).

---

## 2 · Heizkörper aus Angeboten den Heizkreisen zuordnen

**Neues Modul:** `backend/app/services/radiator_matching.py`

- Parst `offer_items.position_label` als `<wohnung>.<hk-nr>`.
- Filter auf Heizkörper-Keywords (`heizk`, `badheizk`, `hk`, `radiator`).
- **Zwei Strategien:**
  - **Direct** (≥80% direkter Match): Wohnungs-Nr im Angebot ↔ `heating_circuit.position`.
  - **Indexed** (sonst): n-te Heizkreis-Position bekommt n-te Wohnungs-Gruppe (verträgt Offset).
- Concat-Format: `2× COSMO Bad… + 2× COSMO Typ 22 K…` (max 255 Zeichen).
- **Auto-Trigger:** in `offer-confirm`, `heating-import-confirm` und nach Section-Schedule-Updates.
- **Manueller Endpoint:** `POST /api/projects/{slug}/heating-design/sync-radiators-from-offers`.

---

## 3 · Material-Stamm aus Angeboten (Auto-Kopie)

**Neue Migration:** `e5c1b3d8a920_material_items_offer_item_link.py`
- `material_items.offer_item_id` FK auf `offer_items.id` (`ON DELETE SET NULL`).

**Neues Modul:** `backend/app/services/offer_to_material.py`
- `sync_offer_to_material(db, offer_id)` — beim Upload werden offer_items als material_items kopiert (`soll_qty = offer.qty`).
- Pauschal-Positionen werden geskippt (`unit in {pauschal, std, h, …}`).
- **Re-Upload-Dedup-Strategie:**
  1. Match per `offer_item_id` (Re-Sync desselben Angebots).
  2. Match per normalisiertem `(article_no, name)` für orphan re-link (z.B. nach Angebots-Delete).
  3. Werkzeug-Einträge (`kind='werkzeug'`) werden NICHT gestohlen.
- **Section-Heuristik:** wenn source_file genau einen Section-Namen enthält → auto-zuweisen.
- **Bulk-Reassign-Endpoint:** `POST /api/projects/{slug}/material-items/bulk-assign-section` (Liste von item_ids + section_number).

**Auto-Trigger:** in `import_offer_confirm`.

---

## 4 · Material-Verbrauchsbuchungen (volle Historie)

**Neue Migration:** `d3f6a9b2c715_material_usages.py`
- Tabelle `material_usages`: `project_id`, `material_item_id` (SET NULL), `daily_report_id` (SET NULL), `user_id` (SET NULL), `section_number`, `qty_used`, `unit`, `used_at`, `notes`.

**Neues Modul:** `backend/app/services/material_usage.py`
- `recalc_ist_qty(db, material_item_id)` → `ist_qty = SUM(usages.qty_used)`.
- `find_material_drift(db, project_id)` → liefert Items wo `stored_ist != computed_ist`.
- `heal_material_drift(db, project_id)` → fixt alle Drifts.

**Endpoints:** in `backend/app/api/domains.py`
- `GET/POST/DELETE /projects/{slug}/material-usages` (CRUD)
- `GET /projects/{slug}/material-analytics` (per_item, per_section, weekly_burndown, top_items)
- `GET /projects/{slug}/material-consistency` (Drift-Check)
- `POST /projects/{slug}/material-recalc-all` (Heilung)

**Auto-Aggregation:** nach jedem POST/DELETE läuft `recalc_ist_qty()` synchron.

**Auto-Assign:** Wenn beim Buchen ein „nicht zugewiesenes" Material verbaut wird, übernimmt `material_items.section_number` den aktuellen Abschnitt.

**ist_qty read-only via PATCH:** `update_material_item` ignoriert `ist_qty` aus dem Payload und rekonstruiert es aus `recalc_ist_qty()`. Verhindert Drift durch UI-Editoren.

---

## 5 · Tagesbericht-Erweiterungen

### 5.1 Team Multi-Select
**Neue Migration:** `f7d2c891b340_daily_report_attendees.py`
- Tabelle `daily_report_attendees` (daily_report × user, unique).

- `DailyReportCreate` Pydantic-Modell um `attendee_user_ids: list[int]` erweitert.
- `create_daily_report` validiert dass IDs Projekt-Mitglieder sind, legt `DailyReportAttendee`-Rows an.
- `_daily_read` liefert `attendee_user_ids` zurück.

### 5.2 Wizard-Step 4 „Material verbaut"
- Frontend (`daily-report-form.component`): neuer Wizard-Step zwischen Tätigkeiten und Status & Senden.
- `MaterialService` (neu) wrappt `/material-items`, `/material-usages`, `/material-analytics`.
- Drafts werden lokal gesammelt, beim Submit als Batch gepostet.
- **Filter „nur dieser Abschnitt"** im Material-Dropdown (Toggle „Alle Abschnitte zeigen").

### 5.3 Submit-Idempotenz (Fix Duplikate)
- **Problem:** Bei Retry nach gescheiterten Anhängen wurde **jedesmal ein NEUER Daily-Report angelegt** (3 Duplikate).
- **Fix:** `savedReportId` merken nach erstem erfolgreichen Report-POST. Beim Retry nur Anhänge nachreichen, kein neuer Report.

### 5.4 Sichtbare Fehler bei Anhang-Failures
- `forkJoin` liefert pro Task `{ok, draftId, error}` statt `null`.
- Bei mind. einem Fehler: deutliche Notification „X von Y Buchungen schlugen fehl — Drafts bleiben im Formular".
- Failed Drafts werden behalten, erfolgreiche entfernt.

---

## 6 · Teamstatus automatisch aus Tagesberichten

- Renderer-Context: `team_users`, `team_days`, `team_status_matrix`.
- Auto-Status: jeder Anwesende eines Tages erbt den Bericht-Status (red > yellow > green Worst-Case).
- Manuelle `TeamStatusEntry`-Rows überschreiben den Auto-Status.
- Template `OBERMONTEUR_Teamstatus.html` komplett umgebaut: Matrix Person × Tag mit Status-Pills, manuelle Korrekturen markiert mit ✎.
- **Bug-Fix:** Auto-Einträge brauchen explizit `manual: False`, `note: None`, `soll_hours: None` als Defaults — sonst Jinja2-`UndefinedError` und ALLE Republishes scheitern stumm (war Ursache für „Sheet zeigt nicht den aktuellen Stand").

---

## 7 · Checkliste pro Abschnitt

- Template `OBERMONTEUR_Checklisten.html`: Akkordeon pro Bauabschnitt × 3 Phasen (Vor Beginn / Ausführung Prüfen / Abschluss).
- 10 Checkboxen + 3 Notiz-Textareas pro Abschnitt → 13 `data-field-id`s pro Section.
- Persistenz über bestehendes `form_responses`-System (kein neues Schema nötig).
- **Field-ID-Schema:** `checkliste.s<n>.<phase>.<feld>`.

---

## 8 · Detaillierter Ablaufplan #4

Template `BAULEITUNG_Detaillierter_Ablaufplan.html` komplett überarbeitet:
1. **Projektinfos** (Hero mit Bauherr/Bauleitung/Verantwortlich/Zeitraum/Stunden).
2. **Mini-Gantt** (Balkenplan pro Abschnitt, schedule-pinned visuell unterschieden).
3. **Abschnittsweise Details** (Ziel, Stunden, Zeitraum, Verantwortlicher, Personal).
4. **Hauptleistung** (Ordered List aller Section-Goals).
5. **Meilensteine** (aus neuer Meilenstein-Engine).

---

## 9 · Meilensteine-Engine

**Neue Migration:** `a8e4b2f1c635_milestones.py`
- Tabelle `milestones`: `type` (`section_end`, `druckpruefung`, `inbetriebnahme`, `custom`), `section_id`, `planned_date`, `actual_date`, `status`.

**Neues Modul:** `backend/app/services/milestones.py`
- `sync_milestones(db, project_id)` — idempotent, 3 Auto-Trigger:
  - `section_end`: planned = section_schedule.end_date oder project.planned_end; actual = wenn alle Checklisten-Phasen abgehakt.
  - `druckpruefung`: actual = wenn `checkliste.s<n>.abschluss.pruefprotokoll_erstellt` gehakt.
  - `inbetriebnahme`: actual = wenn alle section_ends done.

**Trigger:** `form_responses` PUT (Checkliste-Häkchen) und `section-schedules` PUT.

**Endpoints:** `GET /milestones`, `POST /milestones/sync`.

Template `PROJEKTLEITUNG_Meilensteinplan.html` neu mit Status-Pills (pending / done / overdue).

---

## 10 · Template-Cleanup (25 → 17 Templates)

**Gelöscht (8):**
- `tagescheckliste`, `wochenplan`, `ablaufplan_abschnitte`, `abschnittsplanung`
- `blocker_offene_punkte`, `risiken_maengel`
- `statusuebersicht`, `projektunterlagen`

**SLUG_TO_FILENAME in `template_publisher.py` aktualisiert.**

---

## 11 · Styling-Überholung (Phase A–D)

### Recherche (Subagent)
Empfehlung: **IBM Carbon Design Tokens** als Basis (passt zu Plex Sans Font), 12 Primitives statt 50 Custom-Styles, Mobile-First-Patterns.

### Phase A — Foundation (`frontend/src/styles.scss`)
- Touch-Target 44 → **48px** (Material 3 Standard), CTAs 56px.
- Inputs: 16px font-size (iOS-Zoom-Schutz), großzügigeres Padding, hover/focus/disabled, Custom-Select-Chevron-SVG, **Error-State** (`.field--error`, `aria-invalid`).
- Checkboxen 20px + Label-Wrap mit min-height 48px.
- **`.btn`-Hierarchie:** `.btn--primary`, `.btn--accent`, `.btn--secondary`, `.btn--ghost`, `.btn--danger`, `.btn--danger-ghost`, `.btn--icon` + Größen `--sm`/`--lg` + `.btn--block`.
- **`.data-table` Auto-Card-Fallback < 768px** (jede Zeile zur Card mit `data-label`-Attribut).
- **Mobile-First:** alle `max-width` → `min-width` Refactor.
- `.form-section` als Container für Form-Gruppen.
- `.pill-toggle` 48px Touch + Focus-Ring.
- Skeleton-Loader Utility-Klassen.
- Alte `_tokens.scss` gelöscht (Karteileiche `#0d6b8f`).

### Phase B — Komponenten-Hotspots
- `daily-reports.component.scss`: komplette Renovierung (Akkordeon-Cards mit Status-Pills, klare Hierarchie, Detail-Sektionen, Foto-Galerie).
- `daily-report-form`: alle inline-Styles raus, Member-Picker als `.pill-row`, Usage-Editor responsive Grid.
- `project-form.component.scss`: `:host ::ng-deep` entfernt, hardcoded px → Vars, Mode-Switch responsive.

### Phase C — Backend BASE_CSS
- Inputs auf 48px, 16px Font, hover/focus/disabled, Custom-Select-Chevron.
- `.btn`-System identisch zum Frontend.
- Tabellen: Sticky-Header (Desktop), auto-overflow-x, `.data-cards`-Klasse für Mobile-Card-View.
- Print-Regeln: Header wiederholen, page-break-inside auf Zeilen, Buttons nicht drucken.
- `.field-row` Mobile-First (1 Spalte default, minmax(180px) ab 640px).
- Hero-Grid 2-spaltig auf 420px.

### Phase D — Polish
- `empty-state` Component auf Design-Tokens umgestellt.
- Skeleton-Loader Klassen.

---

## 12 · Sheet-Navigation: Back-Bar

- Top-fixierter Banner im jeden generierten HTML mit:
  - **„← Zurück"** Button (history.back() oder Fallback zu `/projects/{slug}`)
  - Dokument-Titel
  - **🖨** Druck-Knopf
- `body { padding-top: 56px }` für Sichtbarkeit.
- `@media print { display: none }` für sauberen Druck.
- Mobile (<480px): Bar schrumpft auf 48px, Titel ausgeblendet.

**Frontend-Änderung:** `openOutputFile` öffnet jetzt **same-tab** (`window.location.href = ...?token=...`) statt `window.open(_blank)`. Vorteile:
- Browser-Back funktioniert
- `?token=…` ist in `window.location.search` → data-api-Forms im Sheet greifen
- PWA-Vollbild bleibt nutzbar

---

## 13 · PWA-Cache-Strategy

`frontend/ngsw-config.json`:
- `outputs` data-group: `performance` → **`freshness`** mit 3s Timeout, 7d Cache als Offline-Fallback.
- War Ursache für „scheint nicht gespeichert" in installierter PWA.

---

## 14 · Bulk-Reassign-Tool im Material-Sheet

Im „Nicht zugewiesen"-Akkordeon:
- **Toolbar:** Filter „Aus Angebot" (zeigt nur Angebote mit noch offenen Positionen + Count), Filter „Name enthält", Counter, Section-Picker, „Zuweisen"-Button.
- Tabelle mit Checkbox-Spalte + „Alle markieren" + Angebot-Spalte.
- Inline-JS: Filter + Markierung + POST `/material-items/bulk-assign-section` + Page-Reload.
- Auto-Republish nach Bulk-Assign.

---

## 15 · Auto-Republish nach Mutations

**Neues Helper:** `_republish_sheets(db, slug)` in `domains.py`.
- Wird nach jeder mutierenden Operation aufgerufen (`create/update/delete material_item`, `bulk_assign_section`, `create/delete material_usage`).
- `try/except: pass` — Republish-Fehler dürfen Haupt-Operation nicht abbrechen.
- Bug entdeckt: Republish scheiterte **stumm** wegen Teamstatus-Template (Punkt 6) → DB war konsistent, Sheets veraltet → Symptom: „wird nicht gespeichert"-Eindruck.

---

## 16 · Permission-Fixes

**Problem:** Endpoints waren auf `SITE_LEAD_ROLES` (admin/projektleitung/bauleitung/obermonteur) — Monteur ausgeschlossen, kann aber genau diejenige Rolle sein die Tagesberichte schreibt.

**Geändert auf `PROJECT_READ_ROLES`:**
- `GET /api/reports/projects/{slug}/members` — Monteur darf seine Kollegen sehen (für Multi-Select).
- `POST /api/projects/{slug}/material-usages` — Monteur darf eigenen Verbrauch buchen.
- `DELETE /api/projects/{slug}/material-usages/{id}` — Monteur darf nur **eigene** Buchungen löschen.

**Bleibt Lead-only:** Material-Items CRUD, Bulk-Reassign, Sections, Schedules, Team-Status-Override.

---

## 17 · Generator-Input-Übersicht

`ProjectRead` erweitert um `GeneratorInputSummary`:
- `upload_count`, `offer_count`, `offer_position_count`, `offers[]`, `heating`, `material_item_count`, `section_count`, `member_count`.

Frontend `project-outputs` zeigt:
- 5 Quellen-Karten (Angebote, Heizlast, Material-Stamm, Bauabschnitte, Mitglieder) mit Counts + Links.
- Aufklappbare Detail-Listen für Angebot-Dateien und Heizlast-Quelle.
- Liste hochgeladener Unterlagen mit Icon (📄 PDF, 📊 XLSX/CSV, 🖼️ Bild).

---

## 18 · Tests

**Neue Datei:** `backend/tests/test_material_abgleich.py` — 11/11 grün.

Coverage:
- Aggregation (basic, zero, overrun)
- Re-Upload-Dedup (keine Duplikate, Section bleibt, Usages bleiben verknüpft)
- Manueller Stamm (Werkzeug wird nicht gestohlen)
- Pauschal-Skip
- Lösch-Resilienz (Offer-Delete, Material-Delete)
- Konsistenz-Check (Drift-Erkennung)

SQLite-FK-PRAGMA via Fixture aktiviert.

---

## 19 · Frontend-Bugfixes

### canGoNext
- **Problem:** war `computed()` Signal aber las Plain-Object-Properties (`this.form.team` etc.). Signal-Tracking funktioniert da nicht → Weiter-Button reagiert erst nach Step-Wechsel.
- **Fix:** als Plain-Method — wird in jedem Change-Detection-Cycle neu evaluiert.

### DailyReportsComponent fehlte ngOnInit
- Berichte wurden nicht geladen wenn `slug`-Input bei Mount nicht als „changed" detected wird.
- **Fix:** `ngOnInit` ergänzt für initialen Load.

### Demo-Defaults raus aus project-form
- `defaultForm()` hatte hardcoded `slug: 'hez-640'`, `name: 'Heizungsmodernisierung'`.
- **Fix:** alle leer — bei „Bearbeiten" wird das echte Projekt geladen, bei „Neu" startet leer.

---

## 20 · Datei-Übersicht

### Neue Files (Code)
- `backend/app/services/radiator_matching.py`
- `backend/app/services/offer_to_material.py`
- `backend/app/services/material_usage.py`
- `backend/app/services/milestones.py`
- `backend/tests/test_material_abgleich.py`
- `frontend/src/app/core/models/material.model.ts`
- `frontend/src/app/core/services/material.service.ts`

### Neue Files (Migrations)
- `backend/alembic/versions/d3f6a9b2c715_material_usages.py`
- `backend/alembic/versions/e5c1b3d8a920_material_items_offer_item_link.py`
- `backend/alembic/versions/f7d2c891b340_daily_report_attendees.py`
- `backend/alembic/versions/a8e4b2f1c635_milestones.py`

### Modifizierte Files (Auszug)
**Backend:**
- `backend/app/db/orm_models.py` (4 neue ORM-Klassen)
- `backend/app/api/projects.py` (Workspace-Mkdir-Reihenfolge, Generator-Input)
- `backend/app/api/domains.py` (Material-CRUD, Usage-CRUD, Bulk-Reassign, Auto-Republish, Permission-Fixes)
- `backend/app/api/offers.py` (Auto-Trigger sync_offer_to_material + apply_radiator_offers)
- `backend/app/api/heating.py` (Auto-Trigger apply_radiator_offers)
- `backend/app/api/reports.py` (Members-Permission, Attendees-Handling)
- `backend/app/api/form_responses.py` (Milestone-Auto-Trigger)
- `backend/app/api/analytics.py` (Material-Analytics-Endpoint)
- `backend/app/services/template_renderer.py` (Material-Aggregate, Teamstatus-Matrix, Milestones-Render, Back-Bar-Injection, Bug-Fix `manual`-Key)
- `backend/app/services/template_publisher.py` (8 Templates aus SLUG_TO_FILENAME)
- `backend/app/models/project.py` (GeneratorInputSummary)
- `backend/app/models/reports.py` (attendee_user_ids)

**Frontend:**
- `frontend/src/styles.scss` (Foundation-Komplett-Refactor)
- `frontend/src/app/app.scss` (Mobile-First)
- `frontend/src/app/features/reports/daily-report-form/*` (Multi-Select, Material-Step, Filter, idempotent retry)
- `frontend/src/app/features/reports/daily-reports/*` (Akkordeon-SCSS, ngOnInit)
- `frontend/src/app/features/project-form/*` (cleanup, Mobile-First)
- `frontend/src/app/features/project-outputs/*` (Upload-Liste, Generator-Input, same-tab open)
- `frontend/src/app/shared/components/empty-state/*` (Tokens)
- `frontend/src/app/core/models/project.model.ts` (GeneratorInputSummary)
- `frontend/ngsw-config.json` (outputs auf freshness)

**Templates in DB (UPDATE):**
- `material_werkzeug` (v4 → v6: Akkordeon, Angebote, Bulk-Reassign-Tool, optgroups)
- `checklisten` (v4: 3-Phasen Akkordeon)
- `teamstatus` (v2: read-only Matrix)
- `detaillierter_ablaufplan` (v3: Mini-Gantt, Meilensteine)
- `meilensteinplan` (v2: Status-Pills)
- `hydraulischer_abgleich` (v2: Heizkörper-Sektion aus Angeboten)

### Gelöschte Files
- `frontend/src/app/shared/styles/_tokens.scss` (Karteileiche)

---

## 21 · Bekannte offene Punkte

- **Pumpen-Sheet beim Heizlast-Import** wird nicht in `heating_designs.pump_model` übernommen (siehe User-Frage).
- **Idempotency-Keys** im Backend wären sauberer als Frontend-`savedReportId` für Duplikat-Schutz (siehe Tagesbericht-Submit).
- **Storage-Permissions** beim Neu-Deployen manuell `chown -R 1000:1000 storage/` nötig — könnte automatisiert werden.
- **MONTEUR_Baustellenhinweise** wurde behalten als „Aushang/PDF für die Baustelle" — aktuell aber kein Workflow es zu drucken (außer manueller Browser-Print).
- **Materialmeldungen** (open-points/material-form) sind aktuell reine Freitext-Eingabe — keine Auswahl aus Angebot. Wenn benötigt: Item-Dropdown ergänzen.
- **8 obsolete Templates** waren vorher in `storage/projects/hez-640/` als veraltete HTMLs sichtbar — diese wurden mit `rm` entfernt.
