# Implementierungsplan: HEZ Projektgenerator

## Phase 1: Technisches Grundgeruest

Ziel: Das System laeuft lokal in Docker und hat eine klare Trennung zwischen Backend, Frontend, Datenbank, Storage und Nginx.

Aufgaben:

1. Docker Compose anlegen.
2. FastAPI-Backend anlegen.
3. Angular-21-Frontend anlegen.
4. PostgreSQL-Service einbinden.
5. Nginx-Service fuer Hauptdomain und Projekt-Subdomains vorbereiten.
6. Storage-Struktur anlegen:

```text
storage/
  uploads/
  workspaces/
  projects/
```

Ergebnis:

```text
docker compose up --build
```

startet alle Basisdienste.

## Phase 2: Projektdatenmodell

Ziel: Das Tool kann ein Projekt strukturiert anlegen und speichern.

Kernobjekte:

```text
Project
ProjectSection
ProjectUpload
GenerationRun
PublishedProject
```

Wichtige Felder:

```text
slug
name
address
responsible
construction_manager
foreman
planned_start
planned_end
sections[]
notes
status
created_at
updated_at
```

Bauabschnitte:

```text
number
name
goal
planned_hours
responsible
staff
notes
```

Regel:

Die Anzahl der Bauabschnitte ist flexibel und kommt ausschliesslich aus den Projektdaten.

## Phase 3: Projektanlage im Backend

Ziel: FastAPI kann einen Projekt-Workspace erzeugen.

Workspace-Struktur:

```text
storage/workspaces/<slug>/
  input.json
  docs/
  output/
```

`input.json` wird aus Formularwerten erzeugt und ist die zentrale Wahrheit fuer den KI-Lauf.

API-Endpunkte:

```text
POST /api/projects
GET  /api/projects
GET  /api/projects/{slug}
POST /api/projects/{slug}/uploads
POST /api/projects/{slug}/generate
POST /api/projects/{slug}/publish
```

## Phase 4: Frontend MVP

Ziel: Eine einfache Angular-Oberflaeche fuer Projektanlage und Generatorstart.

Views:

```text
Projektliste
Projekt anlegen
Projekt bearbeiten
Bauabschnitte verwalten
Unterlagen hochladen
Generatorlauf starten
Generatorstatus anzeigen
Projekt oeffnen
```

Formularregeln:

```text
Slug ist Pflicht und eindeutig.
Mindestens ein Bauabschnitt ist Pflicht.
Bauabschnitte koennen hinzugefuegt, entfernt und sortiert werden.
Geplante Stunden sind je Abschnitt optional, aber empfohlen.
Fehlende technische Daten werden spaeter als offene Punkte im Output ausgewiesen.
```

## Phase 5: Codex CLI im Backend

Ziel: Das Backend kann Codex CLI kontrolliert starten.

Docker-Anforderung:

```text
Python
FastAPI
Node.js/npm
@openai/codex
Git
Codex config/auth
```

Aktueller Umsetzungsstand:

```text
Backend-Dockerfile installiert @openai/codex.
CODEX_PROFILE ist ueber .env konfigurierbar.
Der Backend-Service nutzt ein persistentes codex_home-Volume.
Der Generator-Endpunkt unterstuetzt Dry-Run und echten Codex-Start.
Der echte Start bleibt bis zur Codex-Authentifizierung im Container deaktiviert.
```

Aufruf:

```bash
codex exec -p hez-generator --cd /storage/workspaces/<slug> --skip-git-repo-check -
```

Der Prompt wird per stdin uebergeben.

Generator-Regeln:

```text
Nutze input.json als zentrale Projektdatenquelle.
Nutze docs/ fuer technische Unterlagen.
Nutze project_docu/ als Referenzschema.
Erzeuge Output nur in output/.
Erzeuge .md und .html.
Keine feste Anzahl von Bauabschnitten.
Fehlende Informationen als offene Punkte markieren.
99_HTML_Uebersicht/index.html muss alle HTML-Dateien verlinken.
```

## Phase 6: Output-Pruefung und Veroeffentlichung

Ziel: Ein Generatorlauf wird nicht ungeprueft veroeffentlicht.

Pruefungen:

```text
output/ existiert
99_HTML_Uebersicht/index.html existiert
Projektuebersicht existiert
Abschnittsordner passen zur Anzahl der Bauabschnitte
HTML-Dateien sind vorhanden
Markdown-Dateien sind vorhanden
```

Veroeffentlichung:

```text
storage/workspaces/<slug>/output/
-> storage/projects/<slug>/
```

## Phase 7: Nginx und Subdomains

Ziel: Jedes Projekt ist ueber eine eigene Subdomain erreichbar.

DNS:

```text
*.hez.tech-artist.de -> Server-IP
```

Nginx:

```text
hez.tech-artist.de
```

zeigt auf das Admin-Frontend.

```text
<slug>.hez.tech-artist.de
```

zeigt auf:

```text
storage/projects/<slug>/99_HTML_Uebersicht/index.html
```

## Phase 8: Persistenz und Versionierung

Ziel: Kein Generatorlauf geht verloren.

Zu speichern:

```text
Inputdaten
Uploads
Prompt
Codex-Profil
Startzeit
Endzeit
Exit-Code
stdout
stderr
Output-Pfad
veroeffentlichte Version
```

Spaeter moeglich:

```text
Version 1
Version 2
Version 3
Vergleich zwischen Versionen
Rollback auf alte Version
```

## Phase 9: Spaetere Erweiterungen

Diese Punkte kommen erst, wenn der Kern funktioniert:

```text
Auswertungen
Dashboard
Projektvergleich
Nutzerrollen
Freigabeprozess
Tagesberichte mit Ruecklauf
Foto-Uploads von Monteuren
n8n-Integration
E-Mail-Versand
PDF-Export
```

## Erste konkrete Umsetzungsschritte

1. Docker-Grundgeruest fertigstellen.
2. Backend-Projektanlage stabil machen.
3. Datenmodell fuer Projekte und Bauabschnitte in PostgreSQL speichern.
4. Angular-Formular fuer Projektanlage bauen.
5. Upload fuer `docs/` bauen.
6. Codex-Dry-Run einbauen.
7. Ersten echten Codex-Lauf mit `project_docu/` als Referenz testen.
8. Output validieren.
9. Projekt unter lokaler Test-Subdomain ausliefern.
