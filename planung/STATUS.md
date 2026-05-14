# Status

Stand: Phase 1 bis Phase 6 MVP-Grundlage umgesetzt.

## Erledigt

```text
Phase 1: Docker/FastAPI/Angular/Nginx Grundgeruest
Phase 2: SQL-Datenmodell fuer Projekte, Bauabschnitte, Uploads, Generatorlaeufe
Phase 3: Backend-API fuer Projektanlage, Listen, Detail, Upload, Generate, Publish
Phase 4: Angular-MVP fuer Projektanlage mit flexiblen Bauabschnitten
Phase 5: Codex CLI Runner mit Dry-Run und echtem Startpfad
Phase 6: Output-Validierung vor Veroeffentlichung
```

## Geprueft

```text
Angular Production Build erfolgreich
Python-Syntaxpruefung erfolgreich
Backend-Direkttest mit SQLite erfolgreich:
- Projektanlage
- Workspace-Erstellung
- Projektliste
- Generator-Dry-Run
```

## Aktuelle Einschraenkungen

```text
Docker ist auf dieser Maschine nicht installiert oder nicht im PATH.
Ein echter Docker-Compose-Start konnte deshalb lokal nicht getestet werden.
Der echte Codex-Lauf braucht im Backend-Container noch Codex-Login und Profilkonfiguration.
PostgreSQL wurde noch nicht im laufenden Docker-Verbund getestet.
```

## Naechste Schritte

```text
1. Docker auf dem Zielsystem pruefen.
2. docker compose up --build ausfuehren.
3. Codex im Backend-Container authentifizieren.
4. Profil hez-generator aus codex/config.toml.example anlegen.
5. Erstes Testprojekt ueber Angular anlegen.
6. Docs hochladen.
7. Generator-Dry-Run pruefen.
8. Ersten echten Codex-Lauf starten.
9. Output validieren und unter Projekt-Subdomain ausliefern.
```
