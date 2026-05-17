# UI/UX-Verbesserung HEZ-Tool — Briefing für KI-Bearbeitung

**Status:** Plan zur Umsetzung. Noch nicht implementiert.
**Sprache:** Deutsch (Frontend-Texte und Code-Kommentare).
**Zielgruppe dieses Dokuments:** Ein KI-Agent, der dieses Dokument liest und die Aufgaben Schritt für Schritt umsetzt.

---

## 1. Projektkontext

Das HEZ-Tool ist eine **Field-Service-Web-App für SHK-Heizungsbau-Projekte** (Sanitär-Heizung-Klima). Eine kleine Firma plant, dokumentiert und überwacht damit Heizungsmodernisierungen in Mehrfamilienhäusern.

### Benutzerrollen

| Rolle | Wer | Typisches Gerät | Tech-Verständnis |
|---|---|---|---|
| **Monteur** | Handwerker auf der Baustelle | Smartphone (oft ältere Geräte, Hände dreckig/Handschuhe) | Sehr niedrig — viele 50+, App-Erfahrung minimal |
| **Obermonteur** | Vorarbeiter | Smartphone + gelegentlich Tablet | Niedrig bis mittel |
| **Bauleitung** | Baustellen-Verantwortlich | Tablet/Laptop, Mischung | Mittel |
| **Projektleitung** | Gesamtverantwortlich | Laptop im Büro | Mittel bis hoch |
| **Viewer** | Externe Einsicht (z.B. Kunde, Behörde) | Browser | Niedrig |
| **Admin** | Inhaber/IT | Laptop | Hoch |

**Worst Case (immer als Maßstab nehmen):** Der 55-jährige Monteur mit Arbeitshandschuhen, der noch nie eine Web-App genutzt hat, draußen bei Sonne auf dem Smartphone-Display, mit schlechter LTE-Verbindung. Wenn er es nicht in 10 Sekunden schafft, ist das UX-Design gescheitert.

### Tech-Stack

- **Frontend:** Angular 21 (Standalone Components, Signals, Router, neue `input()`/`output()`-API), SCSS pro Komponente, keine zusätzliche UI-Library (kein Material, kein Tailwind), eigene Designsprache via globaler `app.scss` + per-Komponente `*.component.scss`.
- **Backend:** FastAPI (Python 3.13), SQLAlchemy 2.0 ORM, Alembic-Migrationen, JWT-Auth (Header `Authorization: Bearer ...`, optional `?token=...` Query für File-Endpoints).
- **Datenbank:** PostgreSQL 17.
- **Deployment:** Docker Compose (postgres, backend, frontend, nginx).
- **Container-Workflow für Frontend-Änderungen:**
  ```bash
  docker compose build frontend && docker compose up -d frontend
  ```
  Hard-Reload (Strg+Shift+R) im Browser nach Build, sonst zeigt der Browser das alte Bundle.
- **Tests:**
  - Backend: `pytest`, Fixtures in `backend/tests/conftest.py` (SQLite-in-memory). Aufruf:
    ```bash
    docker run --rm -v "$PWD/backend/tests:/app/tests:ro" hez-640-backend python -m pytest tests/ -q
    ```
  - Frontend: keine Test-Pflicht für UI-Aufgaben — der manuelle Smoke-Test im Browser zählt.

### Wichtige Konventionen im bestehenden Code

- **Standalone Components** überall. Keine Module verwenden.
- **Signal-basierte State** (`signal()`, `computed()`, `input()`). Bei neuen Komponenten denselben Stil.
- **Imports im Component-Decorator**: alle Abhängigkeiten dort listen, nicht über NgModule.
- **Texte deutsch**, technisch korrekt, aber Benutzer-freundlich (keine Tech-Begriffe).
- **Keine Emojis im Code** außer als bewusste UI-Marker (z.B. die Doku-Typ-Badges 📋/📄).
- **Keine Backwards-Compat-Hacks** bei Refactorings: alte ungenutzte Methoden komplett entfernen, nicht nur als `_unused` markieren.
- **`replace_all: false`** beim Editieren reicht meistens; bei Mehrfach-Matches genauer Kontext oder `replace_all: true`.

---

## 2. Aktueller Zustand — was funktioniert, was nicht

### Was bereits gut ist (nicht kaputt machen)

- **Monteur-Landing** (`frontend/src/app/features/role-landing/monteur-landing.component.html`): klare Action-Cards für „Tagesbericht ausfüllen / Material melden / Blocker melden". Den Stil auf die anderen Seiten ziehen.
- **Privacy-by-Default-System** (PII-Tokenisierung): alle generierten Dokumente liegen anonymisiert auf der Platte. Rollen-basierte Re-Identifikation läuft beim File-Serve. **Dieses System nicht umbauen** — nur drumherum die Anzeige verbessern.
- **Form-Sync-Snippet** (`backend/app/services/form_sync_snippet.py`): wird in jedes ausgelieferte HTML vor `</body>` injiziert; speichert Checkbox-/Text-Eingaben automatisch via `/api/projects/<slug>/form-responses/...`. Funktioniert, aber Status-Feedback ist diskret (kleiner Toast, grüner Hintergrund). Hier ist Platz für eine prominentere, beruhigende Status-Anzeige.
- **PWA-Offline-Banner**: zeigt sich, wenn Browser meldet `navigator.onLine === false`. Bleibt unsichtbar wenn online — siehe Punkt 4 unten.

### Aktuelle Schmerzpunkte (priorisiert)

#### S1. Login-Seite wirkt wie Admin-Backend

`frontend/src/app/app.html` Zeilen 1–21:
- Header sagt „Projektzentrale" mit Subtitle „Projekte, DB-Auswertung, Ausgaben und Rollen sauber getrennt in einem Dashboard." → klingt nach DB-Tool.
- Login-Felder sind in `loginForm = { username: 'admin', password: 'admin' }` vorbelegt (`frontend/src/app/app.ts` Zeile 36). Dev-Convenience, für End-User verwirrend.
- Kein Logo, kein Icon, keine Bauchbinde, dass das eine Werkzeug-App ist.

#### S2. Top-Nav mit 7 Tabs ist überladen

`app.html` Zeilen 29–37 — sieben Routen-Links: Übersicht / Meine Baustellen / Querschnitt / Projekte / Analysen / Generator & Ausgaben / Administration. Für Monteur ist davon **nur „Meine Baustellen" relevant**. Begriffe wie „Querschnitt", „Generator & Ausgaben" sind Tech-Vokabular.

#### S3. Status-Vokabular technisch

`frontend/src/app/shared/utils/format.ts` Funktion `statusLabel()`:
```
filtering: 'Filter-Pipeline',
generation_failed_partial: 'Generator teilweise fehlgeschlagen',
```
Verständlich für Entwickler, abschreckend für Anwender.

#### S4. Fehlermeldungen sind Roh-JSON

Wenn der Token abgelaufen ist, sieht der Anwender im Browser-Tab `{"detail":"Not authenticated"}`. `frontend/src/app/core/services/error-format.ts` formatiert HTTP-Fehler nur grob; Recovery (z.B. „Neu anmelden"-Button) fehlt.

#### S5. Kein dauerhafter Online/Sync-Status

`frontend/src/app/app.html` hat ein `<section class="offline-banner" *ngIf="!online()">` — also nur sichtbar **wenn offline**. Der Monteur weiß nicht, ob sein letzter Bericht angekommen ist. Best Practice: dauerhafter Indikator mit Zeitstempel.

#### S6. Header ist 200px hoch, blockiert Mobile

`app.scss` Zeile ~21: `min-height: 190px` für `.header-copy`. Auf einem iPhone SE mit 568px Höhe bleibt für Inhalt nur ein Streifen. Es gibt **keine erkennbaren Media-Queries für Mobile** im globalen Stylesheet.

#### S7. Bottom-Nav fehlt

Auf Mobile wandert die Daumen-Reichweite zum unteren Bildschirmrand. Top-Tabs sind dort schwer treffbar. Bottom-Tab-Bar ist Standard in App-Designs (siehe ServiceTitan, Jobber, Procore-Mobile).

#### S8. Auto-Save-Feedback diskret

Das eingespielte Form-Sync-Snippet (von der Backend-Seite injiziert in jedes HTML) zeigt:
- Kleinen Toast unten rechts „Gespeichert" für 1,8 Sek.
- Grünen Hintergrund am Feld

Für „kein Tech-Verständnis"-User reicht das nicht. Besser: prominente Statusleiste „✓ Alle Eingaben gesichert um 14:32" oder „⏳ Wird gespeichert…"

#### S9. Keine Onboarding-Tour

Beim ersten Login keine Erklärung. Anwender sieht nur die Listen.

#### S10. Empty States ohne nächsten Schritt

Beispiel `monteur-landing.component.html` Zeile 36:
```html
<p class="empty" *ngIf="outputs().length === 0">
  Noch keine veroeffentlichten Unterlagen fuer dich.
</p>
```
Sagt was nicht da ist, sagt nicht was zu tun ist.

#### S11. Pflichtfeld-Markierung unklar in Formularen

Existierende Formulare (Daily-Report-Form etc.) markieren Pflichtfelder nicht eindeutig. Anwender füllt aus, klickt „Speichern", bekommt Validierungsfehler — frustrierend.

#### S12. „Foto hochladen" ist disabled

`monteur-landing.component.html` Zeile 14–17: Action-Card disabled mit Untertitel „Demnächst". Disabled-Buttons sind frustrierend — entweder funktionsfähig machen oder ausblenden bis Feature da ist.

---

## 3. Industrie-Patterns / Recherche

Folgende Patterns sind in vergleichbaren Field-Service-/Bau-Apps etabliert und gut dokumentiert:

| Pattern | Vorbild | Begründung |
|---|---|---|
| **One primary action per screen** | ServiceTitan, Jobber, Stripe Dashboard | Reduziert kognitive Last; Anwender weiß sofort, was als nächstes kommt |
| **Bottom-Tab-Bar (mobile)** mit 3–5 Tabs | Jobber, Housecall Pro, iOS/Android-Default | Daumen-Reichweite, große Tap-Targets |
| **Plain Language statt System-Sprache** | GOV.UK Design System, Mailchimp | „Daten werden vorbereitet" statt „Filter-Pipeline läuft" |
| **Hidden Permissions sichtbar als „disabled mit Begründung"** | Salesforce, Linear | „Administration (nur Admin-Rolle)" — Anwender sieht: gibt's, ist nichts für mich |
| **Empty States mit nächstem Schritt** | Slack, Trello, Notion | Statt „leer" immer Vorschlag + Button |
| **Forgiveness: Undo statt Confirm** | Gmail (Send Undo), Notion | Snackbar „Bericht gelöscht. [Rückgängig]" 5 Sek. lang |
| **Sync-Status dauerhaft sichtbar** | Notion, Dropbox, Google Docs | Anwender vertraut nur, was sichtbar ist |
| **Schritt-für-Schritt-Wizards** für Erfassung | TurboTax, Typeform, Stripe Onboarding | Senkt Abbruchrate dramatisch |
| **Persistent Project-Context im Header** | Linear, GitHub, Jira | Statt URL-Slug merken → klar im UI |
| **Mobile-first: 44px Tap-Targets, 16px Mindest-Schriftgröße** | Apple HIG, Material Design | Bedienbarkeit mit Handschuhen / dreckigen Fingern |
| **Helper-Tooltips als „?"-Icon** | GOV.UK, Stripe | Erklärung im Kontext, kein Doc-Suchen |
| **Onboarding-Coachmarks** beim ersten Login | iOS-Apps, Slack | Erste 30 Sekunden entscheiden über Akzeptanz |
| **Error in Aktionssprache** mit Recovery-Button | Stripe, Linear | „Verbindung verloren. [Erneut versuchen]" statt Stack-Trace |
| **Sticky Save-Bar** unten | Webflow, Figma | Save-Status + Buttons immer in Sicht |

**Apple Human Interface Guidelines** und **Material Design** sind die zwei Standardreferenzen. Beide haben deutsche Übersetzungen ihrer Begriffe in lokalisierten OS-Versionen, die als Vorbild für die Texte dienen können.

---

## 4. Roadmap mit detaillierten Tasks

### Tier 1 — Quick Wins (ca. 1 Arbeitstag zusammen)

Diese Aufgaben sollten zuerst gemacht werden. Sie sind klein abgegrenzt, haben hohe Wirkung, und brechen nichts.

#### T1.1 Login-Seite freundlich gestalten

**Dateien:**
- `frontend/src/app/app.html` (Zeilen 2–21)
- `frontend/src/app/app.ts` (Zeile 36 — `loginForm`)
- `frontend/src/app/app.scss` (Stile für `.header-copy`, `.login-card`)

**Aufgaben:**
1. `loginForm = { username: '', password: '' }` (keine Dev-Defaults).
2. Header-Texte tauschen:
   - Eyebrow: `Baustellen-App` statt `HEZ Projektgenerator`
   - H1: `Willkommen` (sichtbar nur wenn nicht eingeloggt) bzw. der bisherige Titel wenn eingeloggt
   - Subtitle: `Melde dich an, um deine Baustellen zu sehen.` (nur wenn ausgeloggt)
3. Login-Card neu strukturieren:
   - Logo/Icon oben (Platzhalter-SVG erstellen oder Unicode-Icon `🏗`)
   - Label-Text: `Benutzername` und `Passwort` (ausgeschrieben statt `Benutzer`)
   - Placeholder-Text in Inputs (`placeholder="z.B. max.mustermann"`)
   - Button-Text: `Anmelden` (so lassen), Button visuell prominenter (größerer Padding, eindeutige Farbe)
4. „Passwort vergessen"-Link (vorerst nur ein `mailto:`-Link an `support@firma.de`-Platzhalter) — User soll nicht im Trockenen stehen.

**Akzeptanzkriterien:**
- Neue Login-Felder sind leer beim Laden
- Header ohne nicht-eingeloggten User zeigt nur die Willkommens-Sektion (kein „DB-Auswertung"-Text)
- Auf Mobile (≤ 480px) ist Login-Card vollbreit, Inputs ≥ 44px hoch

#### T1.2 Status-Labels in Plain-Deutsch

**Datei:** `frontend/src/app/shared/utils/format.ts`, Funktion `statusLabel()` Zeilen 28–48.

**Aufgaben:** Übersetzung wie folgt anpassen:
```ts
draft: 'Entwurf',
generated: 'Dokumente erstellt',
generation_queued: 'Wartet auf Erzeugung',
filtering: 'Bereite Daten vor …',
generating: 'Dokumente werden erzeugt …',
running: 'Dokumente werden erzeugt …',
publishing: 'Wird veröffentlicht …',
completed: 'Fertig',
succeeded: 'Fertig',
failed: 'Fehlgeschlagen — bitte erneut starten',
failed_partial: 'Teilweise fertig — Details ansehen',
generation_failed: 'Erzeugung fehlgeschlagen',
generation_failed_partial: 'Erzeugung teilweise fehlgeschlagen',
publish_failed: 'Veröffentlichen fehlgeschlagen',
published: 'Veröffentlicht',
```

**Akzeptanzkriterien:**
- Keine Strings mit „Pipeline", „Run", „Generator" mehr sichtbar für End-User
- Status-Pills auf der App bleiben funktional (Farben unverändert)

#### T1.3 HTTP-Fehlermeldungen verbessern

**Dateien:**
- `frontend/src/app/core/services/error-format.ts`
- `frontend/src/app/core/services/notification.service.ts`

**Aufgaben:**
1. In `formatHttpError(response, fallback)`:
   - 401 → `'Deine Sitzung ist abgelaufen. Bitte neu anmelden.'`
   - 403 → `'Diese Aktion ist für deine Rolle nicht freigegeben.'`
   - 404 → `'Nicht gefunden — vielleicht wurde es verschoben oder gelöscht.'`
   - 422 → bei Form-Validierung: konkrete Feldfehler aus `response.error.detail` extrahieren und freundlich formulieren
   - 5xx → `'Server-Problem. Bitte in einer Minute nochmal versuchen.'`
   - 0 / NetworkError → `'Keine Verbindung. Prüfe deine Internetverbindung.'`
2. `NotificationService` um optionalen `actionLabel` + `actionCallback` erweitern:
   ```ts
   showError(text: string, action?: { label: string; callback: () => void })
   ```
3. Bei 401-Fehlern automatisch Action-Button „Neu anmelden" einblenden, der zur Login-Seite navigiert und Token löscht.
4. Notification-Toast in `app.html` so erweitern, dass der Action-Button gerendert wird.

**Akzeptanzkriterien:**
- Anwender sieht nie mehr Roh-JSON
- 401-Fehler hat sichtbaren „Neu anmelden"-Button

#### T1.4 Rollenabhängige Nav

**Dateien:**
- `frontend/src/app/app.html` (Nav-Block Zeilen 29–37)
- `frontend/src/app/app.ts` (neue `computed`-Signals)

**Aufgaben:**
1. Neue Computed-Signals pro Tab-Sichtbarkeit. Regeln:
   - `Übersicht`: alle
   - `Meine Baustellen`: alle eingeloggten
   - `Querschnitt`: nur `bauleitung`, `projektleitung`, `admin` (bleibt wie es ist mit `canSeeOverview()`)
   - `Projekte`: nur `bauleitung`, `projektleitung`, `admin`
   - `Analysen`: nur `bauleitung`, `projektleitung`, `admin`
   - `Generator & Ausgaben`: nur `projektleitung`, `admin` — umbenennen in `Dokumente erzeugen`
   - `Administration`: nur `admin` — bleibt
2. Statt verstecken: für Rollen ohne Zugriff `disabled` rendern mit Tooltip („Nur für Projektleitung"). Implementierung als `<span>` statt `<a>` mit `aria-disabled="true"` + CSS-Stil grau.
3. Tab `Meine Baustellen` als visuell hervorgehoben (z.B. fetter, leicht andere Farbe) — das ist die Haupt-Aktion für die meisten User.

**Akzeptanzkriterien:**
- Monteur sieht „Meine Baustellen" hervorgehoben, die anderen Tabs grau (mit Tooltip)
- Admin sieht alles, voll funktional

#### T1.5 Sichtbarer Sync-Status oben rechts

**Dateien:**
- `frontend/src/app/app.html` (Header)
- `frontend/src/app/app.ts` (Sync-Tracking)
- `frontend/src/app/app.scss`

**Aufgaben:**
1. Neuer Service `SyncStatusService` (`frontend/src/app/core/services/sync-status.service.ts`):
   - `lastSyncAt = signal<Date | null>(null)`
   - `pendingCount = signal<number>(0)`
   - `setSynced()`, `incrementPending()`, `decrementPending()` als Methoden
2. Im Auth-Interceptor: nach jedem erfolgreichen Response `setSynced()` triggern.
3. Im App-Header (rechts oben, neben User-Card):
   ```html
   <div class="sync-indicator" [class.offline]="!online()">
     <span class="dot"></span>
     <span class="text">
       {{ online() ? 'Online · zuletzt synchronisiert ' + lastSyncRelative() : 'Offline · ' + pendingCount() + ' Berichte warten' }}
     </span>
   </div>
   ```
4. `lastSyncRelative()` als `computed`-Signal: „vor 12 Sek.", „vor 2 Min.", etc.

**Akzeptanzkriterien:**
- Anwender sieht JEDERZEIT, ob er online ist und wann das letzte Mal synchronisiert wurde
- Offline-Zustand zeigt Anzahl wartender Berichte
- Im Print-Layout (PDF-Export) ist der Indikator unsichtbar (`@media print { .sync-indicator { display: none; } }`)

#### T1.6 „Foto hochladen" entscheiden

**Datei:** `frontend/src/app/features/role-landing/monteur-landing.component.html` Zeilen 14–17.

**Aufgaben:**
- Entweder Action-Card aktivieren und auf einen Upload-Workflow verlinken (gibt es schon — Foto-Upload existiert pro Tagesbericht)
- Oder den Card komplett entfernen, bis es als Standalone-Feature existiert
- Empfehlung: **entfernen**, da „Foto direkt zum Tagesbericht" beim Bericht-Erstellen ohnehin möglich ist.

**Akzeptanzkriterien:**
- Keine disabled-Buttons mehr auf Monteur-Landing

---

### Tier 2 — Strukturveränderungen (jeweils 1–2 Tage)

#### T2.1 Login leitet direkt auf rollenspezifisches Home

**Datei:** `frontend/src/app/app.ts`, Methode `login()` Zeile 63.

**Aktuell:** Nach Login → `router.navigate(['/landing'])`. Dort wird bei genau 1 Projekt auf `/projects/<slug>/role` redirected (siehe `role-landing.component.ts` Zeilen 75–87).

**Gewünscht:**
- Login → direkt auf die richtige Seite je Rolle:
  - Monteur/Obermonteur: `/landing` (zeigt seine Baustellen-Liste oder bei einem Projekt direkt die Role-Landing)
  - Bauleitung/Projektleitung: `/overview/all` (Querschnitt)
  - Admin: `/admin`
- Logik in `app.ts` `login()` einbauen.

#### T2.2 Bottom-Tab-Bar auf Mobile

**Dateien:**
- `frontend/src/app/app.html` (zweite Nav-Sektion einbauen)
- `frontend/src/app/app.scss` (Media Queries)

**Aufgaben:**
1. Bottom-Nav-Komponente einbauen, die auf Bildschirmen ≤ 768px erscheint und die Top-Nav versteckt.
2. Maximal 4 Tabs, je nach Rolle:
   - Monteur: 🏠 Heute · 📋 Berichte · 📷 Fotos · ⚙️ Mehr
   - Bauleitung: 🏗 Baustellen · 📊 Status · 💬 Berichte · ⚙️ Mehr
3. CSS: `position: fixed; bottom: 0; left: 0; right: 0;`, mit `safe-area-inset-bottom` für iPhone-Notch.
4. Inhalt-Container braucht `padding-bottom: 72px` damit Inhalt nicht von Nav überdeckt.

**Akzeptanzkriterien:**
- Auf Smartphone-Größen ist die Top-Nav versteckt, stattdessen Bottom-Nav unten
- Tap-Targets ≥ 44px hoch

#### T2.3 Tagesbericht-Wizard

**Dateien:**
- `frontend/src/app/features/reports/daily-report-form/daily-report-form.component.ts`
- entsprechendes `.html` und `.scss`

**Aufgaben:**
1. Aktuelles Formular in 4 Schritte zerlegen:
   1. **Wann?** Datum (heute vorbelegt), Abschnitt
   2. **Wer + wie viel?** Mitarbeiter, geleistete Stunden
   3. **Was?** Was wurde gemacht, Material, Probleme
   4. **Status + Senden** Ampel grün/gelb/rot, optionale Foto-Aufnahme, „Senden"
2. Fortschrittsbalken oben („Schritt 2 von 4")
3. Jeder Schritt hat „Zurück" + „Weiter"-Button
4. Letzter Schritt hat „Bericht abschicken"-Button (groß, primärfarben)
5. Möglichkeit, jeden Schritt zu speichern und später weiterzumachen (lokaler Draft)

**Akzeptanzkriterien:**
- Anwender wird durch jeden Schritt geführt, kann nicht in einen ungültigen Zustand kommen
- Pflichtfelder pro Schritt werden klar markiert (roter Punkt)
- Beispieltexte/Platzhalter geben Orientierung

#### T2.4 Doku-Liste mit Typ-Badges und Sortierung

**Dateien:**
- `frontend/src/app/features/role-landing/*-landing.component.html` (alle 5 Rollen)
- Neuer Service oder Helper, der Doku-Typ aus Dateinamen/Pfad inferiert

**Aufgaben:**
1. Helper-Funktion `inferDocumentType(path: string): 'form' | 'info'`:
   - Patterns für Form: `*Tagescheckliste*`, `*Wochenplan*`, `*Checklist*`, `*Protokoll*`, `*Risiken*`, `*Maengel*`, `*Status*`
   - Alles andere → `'info'`
2. In der Doku-Liste pro Eintrag ein kleines Badge: 📋 (Form, primärfarben) oder 📄 (Info, neutralgrau)
3. Sortierung: Form-Dokumente nach oben, dann Info-Dokumente
4. Optional: Filter-Toggle „Nur ausfüllbare zeigen"

**Akzeptanzkriterien:**
- Anwender sieht sofort, welche Dokus er bearbeiten muss
- Konsistent über alle Rollen-Seiten

#### T2.5 Empty States mit Call-to-Action

**Dateien:** alle Komponenten, die `<p class="empty">` verwenden.

**Aufgaben:**
- Jeden Empty-State umbauen zu Empty-State-Komponente mit:
  - Icon
  - Erklärungstext (warum ist es leer)
  - Primärer Button („Jetzt starten" o.ä.)
- Vorgeschlagene Empty-State-Komponente: `frontend/src/app/shared/components/empty-state/empty-state.component.ts`
  ```html
  <div class="empty-state">
    <div class="empty-icon">{{ icon() }}</div>
    <h3>{{ title() }}</h3>
    <p>{{ description() }}</p>
    <button class="primary" (click)="action.emit()">{{ actionLabel() }}</button>
  </div>
  ```

#### T2.6 Auto-Save-Status prominenter

**Datei:** `backend/app/services/form_sync_snippet.py` — das JS-Snippet hat aktuell einen kleinen Toast unten rechts.

**Aufgaben:**
1. Statusleiste oben sticky einbauen (statt nur Toast):
   - Default: „✓ Alle Eingaben gesichert um HH:MM"
   - Während Speichern: „⏳ Wird gespeichert …"
   - Bei Fehler: „⚠ Konnte nicht speichern — [Erneut versuchen]"
2. Pro Feld weiterhin grüner/roter Highlight, aber deutlicher animiert (kurze Pulse).

---

### Tier 3 — Größere Investitionen (mehrere Tage)

#### T3.1 Onboarding-Tour

- Library-Empfehlung: `driver.js` (klein, framework-frei, gut dokumentiert) oder `intro.js`. Beide MIT-lizensiert.
- Tour beim ersten Login pro Rolle. „Skip"-Button.
- LocalStorage-Flag `onboarding_completed_v1` setzen, damit nicht jedes Mal triggert.
- Inhalt 5–6 Schritte: Sync-Indikator, Hauptaktion, Berichte-Liste, Hilfe-Button, Abmelden.

#### T3.2 In-App-Hilfecenter

- Neue Route `/hilfe` mit:
  - FAQ-Akkordion pro Rolle
  - Eingebettete Erklär-GIFs/Videos (vom Anwender bereitzustellen, hier nur die Slots vorsehen)
  - Kontakt-Button („Bei Problemen anrufen: [Tel]")

#### T3.3 Offline-First mit Service Worker

- PWA-Manifest + Service Worker (Angular bringt `@angular/service-worker` mit).
- Strategie: Daten-API → Network-First mit Cache-Fallback; statische Assets → Cache-First.
- Schreibende Requests (POST/PUT/DELETE) bei Offline in IndexedDB-Queue, beim Online-Werden replayen.
- Konflikt-Strategie definieren (last-write-wins reicht für MVP).

#### T3.4 Command Palette (Cmd+K)

- Library: `@ngneat/dialog` oder eigenständige Lösung.
- Such-Index: Projekte, Dokumente, letzte Berichte.
- Nur sichtbar für Power-User-Rollen (Bauleitung, Projektleitung, Admin).

---

## 5. Designsystem / Konsistenz

Damit die Verbesserungen nicht zu einem Flickenteppich werden, brauchst du grundlegende Tokens. Falls noch nicht definiert, mit minimalem Umfang ergänzen in `frontend/src/styles.scss` oder `frontend/src/app/app.scss`:

```scss
:root {
  // Farben
  --color-primary: #1769aa;        // CTA-Buttons, aktive Tabs
  --color-primary-hover: #145486;
  --color-success: #1d8a4a;        // Sync-OK, grüner Status
  --color-warning: #c87f00;        // gelber Status
  --color-danger: #b14040;         // Fehler, roter Status
  --color-text: #1a1a1a;
  --color-text-muted: #5b6770;
  --color-bg: #f5f7f5;
  --color-bg-elevated: #ffffff;
  --color-border: #d9e0d8;

  // Spacing
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;

  // Typography
  --font-base: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --text-sm: 14px;
  --text-base: 16px;
  --text-lg: 18px;
  --text-xl: 22px;

  // Radius / Shadow
  --radius-sm: 6px;
  --radius-md: 12px;
  --radius-lg: 18px;
  --shadow-sm: 0 2px 4px rgba(0,0,0,.05);
  --shadow-md: 0 8px 24px rgba(0,0,0,.08);

  // Touch
  --tap-min: 44px;
}
```

Bestehende SCSS-Dateien sollten schrittweise auf diese Variablen migrieren — **nicht in einem Rutsch**, sonst ist die PR zu groß zum Review.

---

## 6. Wichtige „nicht kaputt machen"-Regeln

| Bereich | Warnung |
|---|---|
| **PII-Tokenisierung** | Nicht das Re-Identify-System anfassen (`backend/app/services/pii_tokenizer.py`, `backend/app/api/projects.py` File-Endpoint). Es ist die Datenschutzgrundlage |
| **Form-Sync-Snippet** | Das Snippet liest URL-Pfad nach Pattern `/api/projects/<slug>/outputs/file/<doc>`. Wenn die Route umbenannt wird, Snippet anpassen |
| **Auth-Token in Query** | Der File-Endpoint akzeptiert `?token=<jwt>`. Niemals in normale API-Endpoints diese Möglichkeit einbauen (Tokens in URLs landen in Logs) |
| **Nav-Highlight für `/projects/<slug>/role`** | Es gibt einen manuellen Class-Bind in `app.ts` (`landingActive()`, `projectsActive()`), der diese Route der „Meine Baustellen"-Tab zuordnet. Bei Routen-Refactor mitziehen |
| **DB-Schema-Änderungen** | Immer Alembic-Migration in `backend/alembic/versions/`. Niemals nur das ORM ändern. Tests laufen lassen (`Base.metadata.create_all` in Tests muss weiter funktionieren) |
| **Test-Fixtures** | SQLite-in-Memory mit `Base.metadata.create_all` als Schema-Quelle. Wenn du eine Migration mit `op.alter_column` schreibst (was SQLite nicht kann), brauchst du keine Test-Anpassung — die Tests umgehen Alembic via `monkeypatch.setattr("app.main.init_db", lambda: None)` |
| **Generator-Prompts** | `backend/app/services/generator_runner.py` `_BASE_RULES` enthält Pflicht-Regeln für LLM-Output. Änderungen wirken erst beim nächsten Generator-Lauf — Auswirkung dem User explizit kommunizieren |
| **Status `failed_partial`** | Es gab einen False-Positive-Bug beim Limit-Check (Heizlast-Werte wie „0429 W" wurden als HTTP 429 erkannt). Die Regex-Patterns in `generator_runner.py::_USAGE_LIMIT_PATTERNS` sind jetzt eng gefasst. Nicht aufweichen |

---

## 7. Empfohlene Reihenfolge zum Anfangen

1. **T1.2 (Status-Labels)** — kleinster Patch, sofort sichtbar überall
2. **T1.3 (Fehlermeldungen)** — beseitigt die häufigste Frustration
3. **T1.1 (Login-Seite)** — erster Eindruck zählt
4. **T1.6 (disabled Buttons entfernen)** — winziger Patch
5. **T1.4 (Nav rolle-abhängig)** — moderates Refactor
6. **T1.5 (Sync-Status)** — neuer Service, mehr Code, aber klar abgegrenzt
7. **T2.1 (Login-Routing)** — vor T2.2, damit Bottom-Nav den richtigen Startpunkt hat
8. **T2.2 (Bottom-Nav)**
9. **T2.5 (Empty States)** — quer durch alle Rollen-Seiten
10. **T2.4 (Doku-Badges)**
11. **T2.6 (Auto-Save-Status)**
12. **T2.3 (Wizard)** — größter Tier-2-Brocken
13. Tier 3 nach Bedarf

**Pro Task:** kleiner Commit, Smoke-Test im Browser (Login → durchklicken). Falls du als KI eine PR erzeugst, immer **vor dem Push** den Frontend-Container rebuilden und im Browser prüfen — TypeScript-Errors werden vom Compiler abgefangen, aber CSS-Probleme oder leere Inhalte siehst du erst im Browser.

---

## 8. Was bei jedem Task zu beachten ist

- **Vor Beginn:** TaskCreate-Tool nutzen (oder einen eigenen Trackingmechanismus) — der Task-Umfang muss klein und abgrenzbar bleiben
- **Beim Editieren:** Read-Tool bevorzugen, Edit-Tool für gezielte Patches
- **Nach Änderung:**
  1. `docker compose build frontend && docker compose up -d frontend` (bei Frontend-Tasks)
  2. Hard-Reload im Browser
  3. Smoke: Login → die geänderte Stelle aufrufen → kein Console-Error im Browser → erwartetes Verhalten
- **Falls Backend involviert:** `docker compose build backend && docker compose up -d backend`, Pytest laufen lassen
- **Commits:** wenn vom Anwender gebeten, in der Sprache des Codes (deutsche Commit-Message bei diesem Projekt)

---

## 9. Was NICHT zu tun ist

- Keine UI-Library einführen ohne Rücksprache (würde 50% des bestehenden Styles ersetzen)
- Keine Tailwind-Migration (komplette CSS-Architektur-Änderung)
- Keine Routes umbenennen, ohne die Form-Sync-Snippet-URL-Parsing-Logik mitzupatchen
- Keine Mehrfach-Tabs (z.B. Lazyloaded-Routes) für Inhalte, die zusammengehören
- Kein Refactor des PII-Systems oder der Role-Resolution
- Keine Disabled-Buttons mit „Demnächst"-Subtitle hinzufügen — entweder funktional oder weglassen

---

## 10. Erfolgsmessung

Diese Verbesserungen waren erfolgreich, wenn:
- Ein Monteur ohne vorherige Einweisung in unter **60 Sekunden** seinen ersten Tagesbericht abschickt
- Die Anzahl der „wie geht das?"-Support-Anrufe pro Woche um mindestens **50%** sinkt
- Niemand mehr Roh-JSON oder Tech-Begriffe sieht
- Der Anwender immer weiß: Bin ich online? Wurde meine Eingabe gespeichert? Was ist meine nächste Aufgabe?

---

**Fragen oder Konflikte zwischen Anforderungen?** Beim User rückfragen, bevor du eine eigene Interpretation umsetzt. Lieber 5 Min nachfragen als 5 Stunden falsch bauen.
