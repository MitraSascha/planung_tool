import subprocess

from app.core.settings import settings


def build_generation_prompt(extra_prompt: str | None = None) -> str:
    prompt = f"""
Du erstellst eine SHK-Projektdokumentation.

Nutze diese Dateien im aktuellen Workspace:
- input.json: strukturierte Projektdaten aus dem Formular
- docs/: technische Projektunterlagen

Nutze das Referenzschema aus:
{settings.reference_schema_path}

Regeln:
- Erzeuge die vollstaendige Dokumentation in ./output/.
- Erzeuge Markdown- und HTML-Dateien nach dem bestehenden Referenzschema.
- Verwende Bauabschnitte ausschliesslich aus input.json.
- Keine feste Annahme wie 3 oder 4 Bauabschnitte.
- Fehlende Daten als offene Punkte ausweisen, nicht frei erfinden.
- HTML-Dateien muessen eigenstaendig im Browser funktionieren.
- Erzeuge eine zentrale Navigation unter 99_HTML_Uebersicht/index.html.
""".strip()

    if extra_prompt:
        prompt = f"{prompt}\n\nZusaetzliche Anweisung:\n{extra_prompt.strip()}"

    return prompt


def run_codex(workspace_path: str, prompt: str) -> subprocess.CompletedProcess[str]:
    command = [
        "codex",
        "exec",
        "-p",
        settings.codex_profile,
        "--cd",
        workspace_path,
        "--skip-git-repo-check",
        "-",
    ]

    if settings.codex_model:
        command[2:2] = ["-m", settings.codex_model]

    return subprocess.run(
        command,
        input=prompt,
        capture_output=True,
        text=True,
        check=False,
        timeout=60 * 30,
    )
