# Issue — Wave 3: PWA-Vereinfachung (Field-Service-UX)

**Status:** offen
**Quelle:** Multi-Agent-Recherche aus 2026-05-16 (siehe `UI_UX_VERBESSERUNG.md` + Audit-Empfehlungen Anthropic Best-Practices)
**Abhängigkeit:** Wave 1 + Wave 2 (Generator-Prompt-Härtung + Multi-Agent-Umbau) sind erledigt.
**Voraussetzung beantwortet:** Monteur wechselt innerhalb einer Session zwischen Projekten → Projekt-Picker bleibt, wir flachen nur die Tiefe.

---

## Ziel

Den Pfad „Login → Tagesbericht abschicken" von heute **6 Screens auf 3-4 Screens** zu kürzen, ohne Funktionalität zu verlieren. Außerdem zwei sekundäre Sichten zusammenführen und sensorisches Feedback (Audio + Voice) für die Baustelle ergänzen.

---

## Aktueller Pfad (Stand 2026-05-16)

```
Login → /              (OverviewComponent)
      → /landing       (RoleLandingComponent — Dispatcher)
      → /projects/:slug/role
                       (RoleLandingComponent erneut, jetzt rollen-spezifisch)
      → MonteurLanding (Action-Cards)
      → /projects/:slug/reports/daily/new
                       (DailyReportFormComponent — jetzt Wizard, 4 Schritte)
```

6 Screens, davon **2 redundante Dispatcher-Schichten** (`/landing` und `/projects/:slug/role` machen beide eine Rolle-Auflösung).

---

## Tasks

### T3.1 — Landing-Dispatcher kollabieren

**Ziel:** `/landing` zeigt direkt den Projekt-Picker (für Multi-Projekt-User), bei genau 1 Projekt redirected automatisch auf `/projects/:slug/role`. Die zweite Dispatch-Schicht in `/projects/:slug/role` bleibt erhalten, weil das URL-Pattern stabil bleiben muss (Form-Sync-Snippet, Nav-Highlight, externe Verlinkungen).

**Dateien:**
- `frontend/src/app/features/role-landing/role-landing.component.ts` — Picker und Dispatcher konsolidieren, doppelte Logik entfernen.
- `frontend/src/app/features/role-landing/role-landing.component.html` — Picker-Markup direkt in den `/landing`-Zweig.
- `frontend/src/app/app.routes.ts` — Routen verbleiben gleich, nur Komponentennutzung sauberer.

**Akzeptanzkriterien:**
- Multi-Projekt-Monteur landet auf `/landing` direkt im Picker (1 Klick zur Baustelle).
- Single-Projekt-Monteur wird automatisch auf `/projects/:slug/role` weitergeleitet (unverändertes Verhalten).
- Aktive Form-Sync-URLs (`/api/projects/<slug>/outputs/file/...`) bleiben funktionsfähig.
- `landingActive()` / `projectsActive()` in `app.ts` weiterhin korrekt.

**Effort:** M | **Impact:** 4

---

### T3.2 — Report-Routes flachklopfen

**Ziel:** Die langen `/projects/:slug/reports/daily/new` und `/projects/:slug/reports/weekly/new` zu einem parametrisierten `/projects/:slug/report/new?type=daily|weekly` zusammenfassen. URL-Tiefe ≤3 ist Mobile-UX-Standard.

**Dateien:**
- `frontend/src/app/app.routes.ts` — zwei Routen zu einer mit Query-Param mergen.
- `frontend/src/app/features/reports/daily-report-form/daily-report-form.component.ts` — Query-Param lesen und konditional Felder/UI anpassen.
- `frontend/src/app/features/reports/weekly-report-form/weekly-report-form.component.ts` — entweder in die Daily-Form integrieren oder als interne Sub-Komponente verbleiben.
- Alle `routerLink`s auf die alten Pfade (grep nach `reports/daily/new`, `reports/weekly/new`).

**Akzeptanzkriterien:**
- Beide Wizards funktionieren über die neue Route.
- Alte Links 301-redirecten (oder werden manuell migriert — keine Toten-Links).
- Wizard-Schritte und Pflichtfeld-Validierung unverändert.

**Effort:** M | **Impact:** 4

---

### T3.3 — `/overview/all` + `/projects` zu „Verwaltung" mergen

**Ziel:** Office-Rollen (Bauleitung/Projektleitung) haben heute zwei Tabs für ähnlichen Zweck: `Querschnitt` (`/overview/all`, Status-Liste) und `Projekte` (`/projects`, CRUD-Liste). Mergen zu einem Hub mit Toggle (Karten ↔ Tabelle).

**Dateien:**
- `frontend/src/app/features/projects-overview/projects-overview.component.ts` + html.
- `frontend/src/app/features/projects-list/projects-list.component.ts` + html.
- `frontend/src/app/app.routes.ts` — `/overview/all` redirected auf `/projects`.
- `frontend/src/app/app.html` — einen Nav-Tab streichen, Bottom-Nav-Slot freimachen.
- `frontend/src/app/app.ts` — `bottomTabs()` Computed-Signals.

**Akzeptanzkriterien:**
- Ein „Verwaltung" oder „Projekte"-Tab im Top-Nav statt zwei.
- Bottom-Nav-Slot für etwas Sinnvolleres frei.
- Karten- und Tabellen-View beide über Toggle erreichbar.
- Filter-Optionen (Status, Suche, Nur-Blocker, At-Risk) bleiben funktional.

**Effort:** L | **Impact:** 3

---

### T3.4 — Audio-Feedback für kritische Aktionen

**Ziel:** Toast-Notifications sind in Sonnenlicht unlesbar (Recherche-Befund). Bei Speichern/Sync-Fail einen kurzen Audio-Cue spielen — robuster als visuelle Bestätigung allein.

**Dateien:**
- Neuer Service `frontend/src/app/core/services/audio-feedback.service.ts` mit `playSuccess()`, `playError()`, `playSyncFail()`.
- `NotificationService.showMessage` ruft `playSuccess()`.
- `NotificationService.showError` ruft `playError()`.
- `SyncStatusService` triggert `playSyncFail()` bei Übergang `online → offline mit pending Berichten`.
- Web-Audio-API mit kurzen synthetisch erzeugten Tönen (kein Asset-Download).
- Mute-Toggle in Push-Settings.

**Akzeptanzkriterien:**
- Kurzer Tick (~80ms, 800Hz) beim erfolgreichen Save.
- Distinktiver Buzzer (~200ms, 250Hz) bei Sync-Fail.
- Default eingeschaltet, deaktivierbar in Settings.
- `@media (prefers-reduced-motion: reduce)` bzw. `Notification.permission === 'denied'` Audio-Default = aus.

**Effort:** S | **Impact:** 3

---

### T3.5 — Voice-Input auf Langtext-Feldern

**Ziel:** Sprache-zu-Text auf allen `<textarea>`-Feldern des Tagesbericht-Wizards. Aufnahme-Button neben dem Feld, browser-natives `webkit-speechrecognition` für Chrome/Edge/Safari.

**Dateien:**
- Neue Komponente `frontend/src/app/shared/components/voice-text-input/voice-text-input.component.ts`.
- `daily-report-form.component.html` Schritt 3: `<textarea>` für `completed_work`, `open_work`, `material_missing`, `blockers`, `notes` mit Mikrofon-Button.
- Fallback wenn API nicht verfügbar: Button ausblenden, kein Fehlerton.

**Akzeptanzkriterien:**
- Mikrofon-Tap startet Aufnahme, Stop-Tap fügt erkannten Text an existierenden Inhalt an (nicht überschreiben).
- Sprache fix `de-DE`.
- Permission-Prompt nur einmal, danach gemerkt.

**Effort:** M | **Impact:** 4

---

### T3.6 — Foto-Button bottom-right Daumenreichweite

**Ziel:** Die Recherche fordert „Foto-Button immer in Daumenreichweite, bottom-right, 64 px". Aktuell ist Foto-Auswahl im Wizard-Schritt 4 versteckt — das Smartphone-Pattern verlangt einen sticky FAB (Floating Action Button) auf allen Daily-/Material-/Blocker-Erfassungsseiten.

**Dateien:**
- Neue Komponente `frontend/src/app/shared/components/photo-fab/photo-fab.component.ts` — `position: fixed; bottom: 88px; right: 16px;` (über Bottom-Nav).
- Integration in `daily-report-form`, `blocker-form`, `material-form`.
- Reuses existing `PhotoService.upload(...)`.

**Akzeptanzkriterien:**
- 64×64 px Button, sichtbar auf allen Erfassungsseiten.
- Sticky position auch beim Scrollen.
- Klick öffnet System-Kamera (input `accept="image/*" capture="environment"`).
- Hochgeladenes Foto landet automatisch im aktuellen Kontext (Bericht/Blocker/Material).

**Effort:** S | **Impact:** 4

---

## Reihenfolge (Empfehlung)

1. **T3.1** zuerst — Landing-Dispatcher kollabieren (Voraussetzung für sauberen Pfad).
2. **T3.2** danach — Report-Routes flachklopfen.
3. **T3.6** — Foto-FAB (klein, sofort spürbar).
4. **T3.4** — Audio-Feedback (klein, sofort spürbar).
5. **T3.5** — Voice-Input (mittelgroß).
6. **T3.3** zum Schluss — Office-Hub-Merge (größter Umbau, betrifft Office-Rollen mehr als Monteure).

---

## Erfolgsmessung

- Monteur-Pfad „Login → Tagesbericht abschicken" ≤ 4 Screen-Wechsel.
- Office-Top-Nav ≤ 5 Tabs.
- Auf Mobile ≥ 1 sensorische Bestätigung pro Save-Aktion (Audio oder Vibrate).
- Voice-Input für Langtext-Felder verfügbar.
