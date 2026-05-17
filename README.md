# HEZ Tool

Dockerisierte Plattform zur Erstellung projektbezogener SHK-Projektdokumentationen.

Das bestehende `project_docu/` dient als Referenzschema. Das Backend legt pro Projekt einen Workspace an, schreibt strukturierte Eingabedaten hinein und startet einen LLM-CLI-Provider (Codex oder Claude Code), um `.md`- und `.html`-Dateien in einer rollenbasierten Ordnerstruktur (`output/00_Start/ ... 05_Allgemein/`) zu erzeugen.

## Zielablauf

1. Projekt im Angular-Frontend anlegen.
2. Formularwerte und technische Unterlagen hochladen.
3. Backend erzeugt `input.json` im Projekt-Workspace.
4. Backend startet den konfigurierten LLM-Provider (Codex CLI oder Claude Code CLI) parallel pro Zieldatei.
5. Generator erzeugt die Dokumentation rollenbasiert in `output/00_Start/ ... 05_Allgemein/`.
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

## LLM-Provider

Der Generator unterstuetzt zwei austauschbare CLI-Provider. Default ist Mixed-Mode — Tasks werden round-robin zwischen beiden verteilt:

```text
LLM_PROVIDER=both    # Default: Codex + Claude gemischt (round-robin pro Task)
                     # Alternativen: codex (nur Codex) oder claude (nur Claude)
GENERATOR_PARALLELISM=3
```

Im Mixed-Mode laufen beide CLIs parallel im selben Generatorlauf. Vorteile: doppelter Throughput (jede CLI hat eigene Rate-Limits), Ausfallsicherheit (faellt ein Provider aus, machen die anderen Tasks weiter), und welcher Provider welchen Task uebernommen hat steht im Run-Log unter `===== <task> [codex|claude] =====`.

Beide Provider werden im Backend-Container installiert:

- `@openai/codex` (Codex CLI)
- `@anthropic-ai/claude-code` (Claude Code CLI)

### Codex CLI

`-p` ist das Codex-Profil aus `config.toml`, nicht der Prompt. Der Prompt wird vom Backend ueber stdin an `codex exec` uebergeben.

```bash
codex exec -p hez-generator --cd /storage/workspaces/hez-640 -
```

Die Vorlage fuer das Codex-Profil liegt unter:

```text
codex/config.toml.example
```

Hinweis fuer Docker: Das Profil `hez-generator` nutzt `sandbox_mode = "danger-full-access"`, weil bubblewrap in vielen Docker-Setups keine unprivilegierten User-Namespaces erstellen kann. Die Eingrenzung erfolgt ueber den Container und die gemounteten Volumes.

### Claude Code CLI

Bei `LLM_PROVIDER=claude` ruft das Backend `claude --print --allowed-tools "Read,Write,Edit,Glob,Grep,Bash,Task" --permission-mode acceptEdits ...` auf und uebergibt den Prompt ueber stdin. Das `Task`-Tool ist freigeschaltet, damit Claude pro Top-Level-Task bis zu `GENERATOR_SUBAGENT_LIMIT` eigene Subagents starten kann.

### Authentifizierung (Host-Bind-Mounts)

Beide CLI-Logins werden direkt aus den globalen Auth-Dateien des Host-Users gezogen. `docker-compose.yml` mountet:

```text
~/.codex          ->  /home/appuser/.codex
~/.claude         ->  /home/appuser/.claude
~/.claude.json    ->  /home/appuser/.claude.json
```

Der Container-User `appuser` laeuft mit UID/GID 1000 (siehe `backend/Dockerfile`, anpassbar via Build-Args `APP_UID`/`APP_GID`), damit die Bind-Mounts ohne Permission-Probleme funktionieren. Wer sich ausserhalb von Docker bereits mit `claude login` und `codex login` angemeldet hat, kann den Backend-Container direkt nutzen, ohne sich nochmal einzuloggen.

Alternative API-Keys via `.env` werden weiterhin akzeptiert:

```text
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
CLAUDE_MODEL=        # optional, sonst Default
```

### Parallele Subagenten

Der Generator zerlegt den Auftrag pro Generatorlauf in einzelne Tasks (eine Task je rollenbasierter Zieldatei-Gruppe). Diese werden parallel als eigene Subprozesse ausgefuehrt (`GENERATOR_PARALLELISM`, Default 4). Jeder Task hat seinen eigenen Prompt und sein eigenes Kontextfenster. Die Navigation in `00_Start/` laeuft am Schluss, nachdem alle Inhalts-Tasks fertig sind. Faellt ein Task aus, brechen die anderen nicht ab; der Lauf endet dann mit `status="failed_partial"`.

## RBAC-Filter fuer Output-Ansicht

Die Output-Liste (`GET /api/projects/<slug>/outputs`) sowie der direkte Datei-Endpoint (`GET /api/projects/<slug>/outputs/file/<pfad>`) werden serverseitig nach der effektiven Rolle des Benutzers gefiltert. Massgeblich ist die Projektrolle (`project_members.project_role`), bei globalen Admins gewinnt die globale Rolle.

```text
monteur         -> 00_Start, 01_Monteur, 05_Allgemein
obermonteur     -> + 02_Obermonteur
bauleitung      -> + 03_Bauleitung
projektleitung  -> alle
admin           -> alle
viewer          -> alle (read-only)
```

Antworten enthalten `visible_folders: list[str]` als Hinweis fuer das Frontend (leere Liste = alle sichtbar). Ein direkter Datei-Aufruf in eine nicht erlaubte Top-Level-Ordnerebene antwortet mit HTTP 403.

## Datenbank-Migrationen

Das Backend nutzt Alembic. Beim Container-Start fuehrt `init_db()` automatisch `alembic upgrade head` aus. Neue Schema-Aenderungen werden ueber `alembic revision --autogenerate -m "<beschreibung>"` im `backend/`-Verzeichnis erzeugt und ins Repo committet.

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
