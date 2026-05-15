# HEZ Tool

Dockerisierte Plattform zur Erstellung projektbezogener SHK-Projektdokumentationen.

Das bestehende `project_docu/` dient als Referenzschema. Das Backend legt pro Projekt einen Workspace an, schreibt strukturierte Eingabedaten hinein und startet spaeter Codex CLI, um `.md`- und `.html`-Dateien nach dem bekannten Schema zu erzeugen.

## Zielablauf

1. Projekt im Angular-Frontend anlegen.
2. Formularwerte und technische Unterlagen hochladen.
3. Backend erzeugt `input.json` im Projekt-Workspace.
4. Backend startet `codex exec -p hez-generator`.
5. Codex erzeugt die Dokumentation in `output/`.
6. Backend veroeffentlicht den Output unter `storage/projects/<slug>/`.
7. Nginx liefert `<slug>.hez.tech-artist.de` aus.

## Lokaler Start

```bash
cp .env.example .env
docker compose up --build
```

Backend:

```text
http://localhost:8000
```

Frontend-Platzhalter:

```text
http://localhost:4200
```

Projekt-Subdomains werden spaeter ueber Wildcard-DNS aktiviert:

```text
*.hez.tech-artist.de -> Server-IP
```

## Codex CLI

Im Backend-Container wird `@openai/codex` installiert. `-p` ist das Codex-Profil aus `config.toml`, nicht der Prompt. Der Prompt wird vom Backend ueber stdin an `codex exec` uebergeben.

Beispiel:

```bash
codex exec -p hez-generator --cd /storage/workspaces/hez-640 -
```

Vor dem ersten echten Generatorlauf muss Codex im Backend-Container authentifiziert und das Profil `hez-generator` angelegt sein. Die Vorlage liegt unter:

```text
codex/config.toml.example
```

Alternativ kann der Backend-Container ueber `.env` mit einem API-Key versorgt werden:

```text
OPENAI_API_KEY=...
```

Der Docker-Service nutzt ein persistentes Volume fuer:

```text
/home/appuser/.codex
```

Damit bleiben Login und Codex-Konfiguration erhalten.

Hinweis fuer Docker: Das Profil `hez-generator` nutzt `sandbox_mode = "danger-full-access"`, weil bubblewrap in vielen Docker-Setups keine unprivilegierten User-Namespaces erstellen kann. Die Eingrenzung erfolgt ueber den Container und die gemounteten Volumes.

## API MVP

Projekt anlegen:

```bash
curl -X POST http://localhost:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{
    "slug": "hez-640",
    "name": "Heizungsmodernisierung",
    "sections": [
      {
        "number": 1,
        "name": "Kellerleitung",
        "planned_hours": 200
      }
    ]
  }'
```

Generator-Dry-Run:

```bash
curl -X POST http://localhost:8000/api/projects/hez-640/generate \
  -H "Content-Type: application/json" \
  -d '{"run_codex": false}'
```
