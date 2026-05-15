import subprocess

from app.core.settings import settings


SMALL_PROJECT_FOLDERS = """
Kleinprojekt-Ausgabe:
- Erzeuge fuer Kleinprojekte einen kompakten, vollstaendigen Satz nur mit diesen Ordnern:
  - 01_Projektuebersicht
  - 06_Detaillierter_Ablaufplan
  - 08_Monteur_Tagescheckliste
  - 10_Tagesbericht_App
  - 11_Meilensteinplan
  - 14_Gantt_Uebersicht
  - 99_HTML_Uebersicht
- Erzeuge keine separaten Abschnittsordner 02_Abschnitt_* bis 05_Abschnitt_*.
- Fuehre alle Arbeitspakete/Bauabschnitte innerhalb von 06_Detaillierter_Ablaufplan, 11_Meilensteinplan und 14_Gantt_Uebersicht.
- Wenn keine docs/Unterlagen vorhanden sind, nutze input.json und weise Annahmen/offene Punkte klar aus.
""".strip()


def build_generation_prompt(project_type: str = "standard", extra_prompt: str | None = None) -> str:
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
- Erzeuge keine externen Automations-Workflow-Dateien.
""".strip()

    if project_type == "small":
        prompt = f"{prompt}\n\n{SMALL_PROJECT_FOLDERS}"

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
