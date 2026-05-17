# Production-Readiness Checkliste
**Stand: 2026-05-17** · **Tool:** Mitra HEZ-Generator

Diese Liste ist nach **Kritikalität** sortiert. Punkte mit 🔴 müssen **vor jeder Produktiv-Nutzung** abgearbeitet sein. 🟡 vor dem Umgang mit Echt-Kunden-Daten. 🟢 und 🔵 sukzessive nach Launch.

Pro Eintrag findest du:
- **Was:** Worum geht's
- **Warum:** Begründung / Risiko
- **Wie:** Konkrete Schritte mit Datei-Pfaden
- **Aufwand:** Realistische Zeitschätzung
- **Status:** Checkbox zum Abhaken

---

## 🔴 KRITISCH — Sicherheit (Tag 1, vor allen anderen Schritten)

### [ ] 1. Default-Passwörter ersetzen
**Was:** Alle DB-User haben aktuell trivial-passende Passwörter (`admin/admin`, etc.).
**Warum:** Wer die Login-URL kennt, ist drin. Sofortiger Lock vor jeder externen Erreichbarkeit.
**Wie:**
1. Im laufenden Container: `docker compose exec backend python -c "from app.services.auth import hash_password; print(hash_password('NEUES_PASSWORT'))"` — gibt einen Hash zurück
2. In DB updaten:
   ```sql
   UPDATE users SET password_hash = 'DER_NEUE_HASH' WHERE username = 'admin';
   ```
3. Für alle 5 User wiederholen
4. **Besser noch:** Endpoint `/api/auth/users` so erweitern, dass Admin via Frontend Passwörter zurücksetzen kann
**Aufwand:** 30 Min (manuell) · 2 h (mit UI-Erweiterung)
**Status:** ☐ offen

### [ ] 2. JWT-Secret durch starkes Random-Secret ersetzen
**Was:** `backend/app/core/settings.py:21` hat `jwt_secret: str = "change-me-in-production"`.
**Warum:** Jeder mit Codezugriff kann gültige Tokens fälschen — auch ohne Login.
**Wie:**
1. Random-Secret generieren: `python -c "import secrets; print(secrets.token_urlsafe(64))"`
2. In `.env` setzen: `JWT_SECRET=<das_secret>`
3. Settings prüft schon auf ENV — wenn `JWT_SECRET` gesetzt ist, überschreibt es den Default
4. Bei Secret-Wechsel: alle aktiven Sessions sind invalidiert — User müssen neu einloggen
**Aufwand:** 5 Min
**Status:** ☐ offen

### [ ] 3. JWT-TTL prüfen / verkürzen
**Was:** Aktuell `jwt_access_token_minutes: int = 480` (= 8 h).
**Warum:** Bei gestohlenem Token max. 8 h Schaden. Für Bauleitung OK, für Admin evtl. kürzer (1-2 h).
**Wie:**
- Aktuell ein globaler Wert. Falls rolle-spezifisch gewünscht: in `app/services/auth.py` `create_access_token()` rolle-abhängig setzen
- Alternativ: Refresh-Token-Mechanismus einbauen (komplexer)
**Aufwand:** 15 Min (Verkürzung) · 4 h (Refresh-Token-Flow)
**Status:** ☐ offen

### [ ] 4. HTTPS erzwingen (Let's Encrypt + nginx)
**Was:** `nginx/default.conf` lauscht aktuell nur auf Port 80 (HTTP).
**Warum:** Passwörter und JWT fließen aktuell im Klartext über die Leitung.
**Wie:**
1. Domain auf Server zeigen lassen (DNS A-Record für `hez.tech-artist.de`)
2. `certbot --nginx -d hez.tech-artist.de` im Container oder als Sidecar
3. nginx-Config erweitern: `listen 443 ssl;` + Cert-Pfade + Redirect von 80 → 443
4. `docker-compose.yml`: Port 443 nach außen freigeben
5. **Cookie-Flag:** Wenn Cookies (auch nur Service-Worker) → `Secure` + `SameSite=Strict`
**Aufwand:** 2-3 h
**Abhängigkeit:** Echter Server mit öffentlicher Domain
**Status:** ☐ offen

### [ ] 5. CORS-Konfiguration setzen
**Was:** Aktuell **keine** `CORSMiddleware` in `backend/app/main.py` registriert.
**Warum:** Im laufenden Setup OK (nginx proxied), aber falls API jemals direkt erreichbar wird → jede Origin kann zugreifen.
**Wie:**
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://hez.tech-artist.de"],
    allow_credentials=True,
    allow_methods=["GET","POST","PUT","PATCH","DELETE"],
    allow_headers=["*"],
)
```
**Aufwand:** 15 Min
**Status:** ☐ offen

### [ ] 6. Rate-Limiting für Login + Import-Endpoints
**Was:** Aktuell unbegrenzte Versuche möglich.
**Warum:** Brute-Force gegen `/api/auth/login`, DoS gegen Upload-Endpoints.
**Wie:**
1. `slowapi` installieren (`requirements.txt`)
2. In `backend/app/main.py`:
   ```python
   from slowapi import Limiter
   from slowapi.util import get_remote_address
   limiter = Limiter(key_func=get_remote_address)
   app.state.limiter = limiter
   ```
3. Auf `/api/auth/login`: `@limiter.limit("5/minute")`
4. Auf Import-Endpoints: `@limiter.limit("20/hour")`
**Aufwand:** 1-2 h
**Status:** ☐ offen

### [ ] 7. Audit: PII-Reveal in allen Endpoints
**Was:** Heute haben wir `_to_project_read` role-aware gemacht. Aber andere Endpoints (Reports, Voice-Notes, Photos, Form-Responses) könnten Klartext liefern.
**Warum:** DSGVO-Pflichten. Ein einziger leaky Endpoint reicht für ein Bußgeld.
**Wie:**
1. Alle `*.py` in `backend/app/api/` durchgehen
2. Prüfen: liefert Endpoint Strings, die `[[PII:...]]` enthalten könnten?
3. Falls ja: vor Response durch `_reveal_pii_for_role()` ziehen
4. Checkliste anlegen pro Endpoint
**Aufwand:** 3-4 h (Audit + Fixes)
**Status:** ☐ offen

### [ ] 7b. Audit: was sehen Codex/Claude wirklich?
**Was:** `backend/app/services/privacy_workspace.py` tokenisiert input.json, heating_design.json, **offers.json (heute fixiert)**, voice_notes.json, photos.json und docs/*.
**Warum:** Cloud-LLMs dürfen NIE Klartext-PII sehen (Art. 6 + 28 DSGVO).
**Wie:**
1. Bei JEDER neuen JSON-Datei im Workspace prüfen ob sie tokenisiert wird (in `prepare_sanitized_generator_workspace`)
2. Zusätzlich: `privacy_manifest.json` nach jedem Run inspizieren — sind alle erwarteten Dateien drin?
3. Stichprobe: einen Run mit echten PII fahren, `generator_input/` Inhalt auf `[[PII:`-Marker prüfen, sicherstellen dass keine Klartext-Adresse/Person drin steht
4. **Bekannte Schwäche:** PII-Tokenizer hat False-Positives (z.B. "Viega Temponox" → PERSON erkannt) UND möglicherweise False-Negatives (seltene Namen, ungewöhnliche Adressen) — periodische Stichproben nötig
**Aufwand:** 2-3 h pro Audit
**Status:** ☐ offen (offers.json-Fix heute, Rest steht)

### [ ] 8. Generator/Codex-Sandbox
**Was:** Codex/Claude führen LLM-generierten Shell-Code aus.
**Warum:** Prompt-Injection-Angriff über manipulierte XLSX → bösartiger Code könnte ausgeführt werden.
**Wie:**
1. Codex-CLI läuft schon im Container — also abgeschottet vom Host
2. Aber: Container hat `/storage`-Mount → Codex könnte alle Projektdateien lesen
3. **Empfohlen:** Pro Generator-Run einen eigenen kurzlebigen Sub-Container ohne Storage-Mount + nur dem aktuellen Workspace
4. Plus: Subprocess-Limits (CPU/RAM/Time) — z.B. via `ulimit` im Wrapper
**Aufwand:** 4-8 h
**Status:** ☐ offen

---

## 🟡 PFLICHT — vor produktivem Einsatz mit Echt-Kunden-Daten

### [ ] 9. Datenbank-Backup-Strategie
**Was:** Postgres-Volume sichern.
**Warum:** Hardware-Fail, versehentlicher DROP, Ransomware. Ohne Backup = totaler Datenverlust.
**Wie:**
1. **Minimal:** Cron-Job: `pg_dump` täglich nach Object-Storage (S3/Backblaze)
   ```bash
   docker compose exec -T postgres pg_dump -U hez hez_tool | gzip > backup-$(date +%F).sql.gz
   ```
2. **Besser:** WAL-Archiving + PITR (Point-in-time-Recovery) z.B. mit `pgBackRest`
3. **Recovery testen** — Backup ohne Test ist kein Backup
4. **Retention:** 30 Tage täglich, 12 Monate monatlich
**Aufwand:** 4 h (Minimal) · 2 Tage (PITR)
**Status:** ☐ offen

### [ ] 10. File-Storage-Backup
**Was:** `storage/`-Volume sichern (Upload-Originale, PDF-Anhänge, generierte HTMLs).
**Warum:** XLSX-Originale können nicht aus DB rekonstruiert werden.
**Wie:**
1. Cron-Job: `tar | gpg | aws s3 cp` nach Object-Storage
2. Inkrementell (z.B. `restic` oder `borg`) statt voll
3. Verschlüsselung vor Upload — Object-Storage-Anbieter sollte nicht lesen können
**Aufwand:** 2 h
**Status:** ☐ offen

### [ ] 11. DSGVO-Workflow end-to-end testen
**Was:** Löschanfrage eines Kunden komplett durchspielen.
**Warum:** DSGVO Art. 17 — "Recht auf Vergessenwerden". Wenn Löschung nicht alle Spuren tilgt, Bußgeldrisiko.
**Wie:**
1. Test-Projekt anlegen mit echten PII (fiktiv aber realistisch)
2. `/api/dsgvo/projects/{slug}/anonymize` aufrufen
3. Prüfen: sind in ALLEN Tabellen + storage-Files keine PII mehr?
4. Tabellen: `projects`, `project_sections`, `project_uploads`, `daily_reports`, `weekly_reports`, `form_responses`, `voice_notes`, `project_photos`, `anonymization_tokens` (die selbst sind tricky!), `audit_events`
5. Files: `storage/workspaces/<slug>/`, `storage/projects/<slug>/`
6. Dokumentieren als Standard-Operating-Procedure
**Aufwand:** 4-6 h
**Status:** ☐ offen

### [ ] 12. Audit-Log auf Vollständigkeit prüfen
**Was:** `backend/app/services/audit_log.py` existiert. Greift es überall?
**Warum:** Bei Datenschutzvorfall muss man nachweisen wer wann was angefasst hat.
**Wie:**
1. Test: User A loggt sich ein, ändert Projekt, lädt Datei hoch, löscht etwas
2. SELECT * FROM audit_events ORDER BY id DESC LIMIT 20
3. Sind alle Aktionen drin?
4. Falls Lücken: in den entsprechenden Endpoints `register_audit_event()` aufrufen
5. **Wichtig:** Audit-Log sollte append-only sein (User soll nicht eigene Spuren löschen können)
**Aufwand:** 2-3 h
**Status:** ☐ offen

### [ ] 13. Auftragsverarbeitungsvertrag (AVV) mit LLM-Anbieter
**Was:** Codex (OpenAI) / Claude (Anthropic) verarbeiten Projektdaten — bevor Anonymisierung greift.
**Warum:** DSGVO Art. 28 — bei Datenverarbeitung durch Dritte muss AVV abgeschlossen sein.
**Wie:**
1. OpenAI: Enterprise/Team-Konto bietet AVV (Data Processing Addendum)
2. Anthropic: Business-Account ebenso
3. Prüfen: läuft Generator über deren API? (Ja, laut Dockerfile `@openai/codex` + `@anthropic-ai/claude-code`)
4. **Alternative:** Lokales LLM (Llama/Mistral) statt Cloud — viel mehr Aufwand
**Aufwand:** 1 h Papierkram + AVV-Unterschrift
**Status:** ☐ offen

### [ ] 14. Strukturiertes Logging (JSON)
**Was:** Aktuell vermutlich text-basierte Logs in stdout.
**Warum:** Bei Vorfall muss man schnell filtern können nach User-ID, Endpoint, Zeitfenster.
**Wie:**
1. `structlog` in `requirements.txt`
2. In `app/main.py`: Logger-Setup mit JSON-Formatter
3. Pro Request: `request_id`, `user_id`, `path`, `status`, `duration_ms`
4. **Wichtig:** KEINE PII in Logs! Niemals `request_body` 1:1 loggen
**Aufwand:** 3-4 h
**Status:** ☐ offen

### [ ] 15. Monitoring + Alerting
**Was:** Aktuell: nichts. Kein Health-Probe, kein Alert wenn Backend down.
**Warum:** "Tool ist seit gestern weg" willst du nicht durch Anruf vom Chef erfahren.
**Wie:**
1. **Healthcheck-Endpoint** existiert schon (`GET /health` in main.py)
2. Uptime-Probe einrichten: UptimeRobot / Better Stack / eigener Cron
3. Error-Tracking: Sentry-Free-Tier (5k Events/Monat reicht für Mitra)
4. `sentry-sdk[fastapi]` in `requirements.txt`, in `main.py` init mit `dsn` aus `.env`
5. Alerts in Slack/E-Mail bei: Backend down, 5xx-Spike, Generator-Run-Fehlerquote >10%
**Aufwand:** 4-5 h
**Status:** ☐ offen

---

## 🟢 ROBUSTHEIT — kurz- und mittelfristig

### [ ] 16. Service-Worker-Cache-Bust
**Was:** Heute hatten wir den "Browser zeigt altes Bundle"-Bug.
**Warum:** Bei jedem Deploy müssen Clients automatisch neue Version ziehen.
**Wie:**
1. In `frontend/ngsw-config.json`: `installMode: "prefetch"` + sichere Versionierung über `ngsw.json` `hash`
2. **Im Frontend-Code:** SwUpdate-Service einbinden:
   ```typescript
   updates.versionUpdates.subscribe(evt => {
     if (evt.type === 'VERSION_READY') { window.location.reload(); }
   });
   ```
3. Optional: User-Toast "Neue Version verfügbar — Aktualisieren?"
**Aufwand:** 2 h
**Status:** ☐ offen

### [ ] 17. Test-Suite aufbauen
**Was:** Aktuell sehr wenig Test-Coverage.
**Warum:** Refactoring ohne Tests = Russisch Roulette.
**Wie:**
1. **Mindest-Coverage:**
   - `backend/tests/test_heating_importer.py` — alle 4 Demo-Dateien als Fixtures
   - `backend/tests/test_offer_importer.py` — die 3 Angebots-Dateien
   - `backend/tests/test_auth.py` — Login, Token-Validation, Rolle-Check
   - `backend/tests/test_pii_role_reveal.py` — PII-Filter pro Rolle
2. **E2E-Smoke:** Cypress oder Playwright — Login → Projekt → Import → Generieren
3. **CI:** GitHub Actions, läuft bei jedem Push, blockiert Merge wenn rot
**Aufwand:** 1-2 Tage (Initial-Setup) + laufend
**Status:** ☐ offen

### [ ] 18. CI/CD-Pipeline
**Was:** Automatischer Build + Test + Deploy bei Git-Push.
**Warum:** Manuelle Deploys produzieren Fehler.
**Wie:**
1. GitHub Actions workflow: `.github/workflows/ci.yml`
2. Jobs: backend-test, frontend-build, docker-build, deploy
3. Migration auto-anwenden beim Deploy (`alembic upgrade head` als Init-Container)
4. Rollback-Plan: vorherige Docker-Image-Tags behalten
**Aufwand:** 1 Tag
**Status:** ☐ offen

### [ ] 19. Alembic-Migrations sauber halten
**Was:** Heute haben wir mehrere Migrations mit Fremd-Änderungen erzeugt (form_responses indexes) und manuell bereinigt.
**Warum:** Schmutzige Migrations → schwer reproduzierbar.
**Wie:**
1. Vor jedem `alembic revision --autogenerate`: ORM-State und DB-State synchron halten
2. Generierte Migration **immer** vor Commit reviewen
3. Bereits angewendete Migrations nicht mehr ändern — neue erstellen
4. Bauphysik-Tabellen wurden via `a7e8b9c0d101` gedroppt — diese Migration als „experimentell" markieren falls sie auf einem Klon-System wieder rauskommt
**Aufwand:** Disziplin · 30 Min Audit der aktuellen Migrations
**Status:** ☐ offen

### [ ] 20. Frontend Error-Boundary
**Was:** Bei API-Fehlern bricht UI teilweise still ab.
**Warum:** Schlechte UX, schwer zu debuggen.
**Wie:**
1. Angular: globaler `ErrorHandler` einsetzen
2. Bei jedem Fehler: Toast/Banner zeigen + an Sentry melden
3. Component-spezifische Fallback-UI ("Etwas ist schiefgelaufen — Neu laden")
**Aufwand:** 4-6 h
**Status:** ☐ offen

### [ ] 21. Form-Validation strikter
**Was:** Frontend validiert minimal, Backend wirft Pydantic-Fehler.
**Warum:** Schlechte UX wenn User erst nach "Submit" Fehler sieht.
**Wie:**
1. Angular Reactive Forms mit Validators
2. Inline-Fehlermeldungen pro Feld
3. Submit-Button erst aktiv wenn Form valid
4. Backend bleibt als Sicherheitsnetz (nie Frontend trauen)
**Aufwand:** 1 Tag (für alle Formulare)
**Status:** ☐ offen

### [ ] 22. Pagination + Suche
**Was:** `/api/projects` lädt aktuell alle Projekte; bei 50+ wird's langsam.
**Warum:** Tool muss auch mit 200+ Projekten gut bedienbar bleiben.
**Wie:**
1. Backend: `?page=1&size=20&search=mareschstr` Query-Parameter
2. Frontend: Pagination-Component, Such-Input
3. SQL: `LIMIT`/`OFFSET`, Suche per `ILIKE` oder Full-Text
**Aufwand:** 4 h
**Status:** ☐ offen

### [ ] 23. File-Upload-Größen-Limit
**Was:** Aktuell vermutlich keine Begrenzung.
**Warum:** User lädt versehentlich 500 MB hoch → Server-OOM.
**Wie:**
1. nginx: `client_max_body_size 20M;` in `nginx/default.conf`
2. FastAPI: pro Upload-Endpoint `MAX_BYTES` prüfen und Early-Reject
3. UI: nach Datei-Wahl Größe prüfen, vor Upload Warnung
**Aufwand:** 1 h
**Status:** ☐ offen

---

## 🔵 UX-POLISH — post-launch, basierend auf User-Feedback

### [ ] 24. Loading-Skeletons statt grauer Wartezeiten
**Wie:** Pro Component ein `*ngIf="loading()"` mit grauen Placeholder-Boxen
**Aufwand:** 2 h
**Status:** ☐ offen

### [ ] 25. Empty-States überall freundlich
**Wie:** Statt leerer Tabelle: "Noch keine Angebote — als erstes XLSX hochladen" mit Button
**Aufwand:** 3 h
**Status:** ☐ offen

### [ ] 26. Onboarding-Tour beim ersten Login
**Wie:** Library `intro.js` oder selbstgemachte Tooltip-Sequenz
**Aufwand:** 1 Tag
**Status:** ☐ offen

### [ ] 27. Tastatur-Shortcuts
**Wie:** `Ctrl+S` zum Speichern, `Ctrl+B` Sidebar toggeln, `Ctrl+K` Quicksearch
**Aufwand:** 4 h
**Status:** ☐ offen

### [ ] 28. i18n vorbereiten
**Wie:** `@angular/localize` einrichten, Texte in `.xlf`-Dateien extrahieren
**Aufwand:** 1 Tag (Initial) + laufende Übersetzungen
**Status:** ☐ offen

### [ ] 29. Dark-Mode (optional)
**Wie:** Bereits Design-Tokens vorhanden → in `prefers-color-scheme: dark` Tokens überschreiben
**Aufwand:** 4-6 h
**Status:** ☐ offen

---

## 📊 BUSINESS / OPERATIVE FEATURES

### [ ] 30. User-Management-UI im Frontend
**Was:** Aktuell muss Admin User per DB anlegen / Passwort zurücksetzen.
**Wie:**
1. Neue Component `admin/user-management/`
2. Liste aller User · Anlegen/Sperren/Rolle ändern · Passwort-Reset-Link generieren
3. Backend: `PATCH /api/auth/users/{id}` Endpoint nachrüsten (existiert noch nicht)
**Aufwand:** 1 Tag
**Status:** ☐ offen

### [ ] 31. DSGVO-Self-Service
**Was:** User können eigene Daten als Export anfordern oder Löschung beantragen.
**Wie:**
1. Profil-Seite: Buttons "Meine Daten herunterladen" / "Konto löschen"
2. Backend-Endpoint: Sammelt alle User-bezogenen Daten als ZIP
3. Löschung mit 30-Tage-Gnadenfrist (Soft-Delete erst, dann hard-delete)
**Aufwand:** 2-3 Tage
**Status:** ☐ offen

### [ ] 32. Reporting / Excel-Export
**Was:** KPI-Dashboards, Excel-Export von Berichten/Angeboten.
**Wie:**
1. Pro Berichts-Typ ein "Export als XLSX"-Button
2. Backend nutzt `openpyxl` (schon installiert)
3. KPI-Dashboard: einfache Card-Übersicht (Anzahl Projekte, Stunden, Heizlast-Summe, Angebots-Summe)
**Aufwand:** 1-2 Tage
**Status:** ☐ offen

### [ ] 33. Multi-Tenant-Modell (langfristig)
**Was:** Falls Mitra mehrere Standorte oder das Tool an andere SHK-Firmen verkauft.
**Wie:**
1. Neue Tabelle `tenants`, alle Datensätze bekommen `tenant_id`
2. Auth: User hat einen Tenant, Queries filtern automatisch
3. Branding pro Tenant (Logo, Farben)
**Aufwand:** 2-3 Wochen (großer Refactor)
**Status:** ☐ offen (nur wenn Bedarf entsteht)

---

## 🗓 Empfohlene Reihenfolge / Wochenplan

### Woche 1 — Sicherheits-Hardening (Items #1-#8)
**Tag 1:** #1 Passwörter · #2 JWT-Secret · #3 JWT-TTL · #5 CORS · #23 Upload-Limit
**Tag 2-3:** #4 HTTPS · #6 Rate-Limiting
**Tag 4-5:** #7 PII-Audit · #8 Generator-Sandbox

### Woche 2 — Daten-Sicherheit (Items #9-#15)
**Tag 1-2:** #9 DB-Backup · #10 File-Backup
**Tag 3:** #11 DSGVO-Test · #12 Audit-Log
**Tag 4:** #13 AVV abschließen · #14 Logging
**Tag 5:** #15 Monitoring + Sentry

### Woche 3 — Qualitäts-Infrastruktur (Items #16-#22)
**Tag 1:** #16 SW-Cache-Bust · #19 Migrations-Cleanup
**Tag 2-3:** #17 Test-Suite Aufbau
**Tag 4:** #18 CI/CD
**Tag 5:** #20 Error-Boundary · #21 Form-Validation

### Woche 4+ — Polish + Features
Nach Bedarf und User-Feedback. #22 Pagination + #30 User-Management sind die wertvollsten.

---

## 💡 Wenn etwas dringend wird (Notfall-Plan)

**Bei Sicherheits-Incident:**
1. Tool sofort offline (nginx down / `docker compose stop`)
2. Logs sichern: `docker compose logs > incident-$(date +%F).log`
3. DB-Snapshot ziehen: `pg_dump > incident-db-$(date +%F).sql`
4. Was wurde wann gemacht: `audit_events` durchgehen
5. Passwörter rotieren, JWT-Secret tauschen
6. Patch deployen, dann erst wieder online

**Bei DSGVO-Anfrage eines Kunden:**
- "Auskunft" (Art. 15): Welche Daten zu Kunde X haben wir? → SELECT aus allen relevanten Tabellen
- "Löschung" (Art. 17): `/api/dsgvo/projects/{slug}/anonymize` + manuelle File-Bereinigung
- **30 Tage Antwortfrist** beachten

---

**Diese Liste lebt.** Beim Abarbeiten gerne Erkenntnisse als Notizen am Ende ergänzen. Items kannst du mit `[x]` abhaken oder mit `(Datum)` markieren wann erledigt.
