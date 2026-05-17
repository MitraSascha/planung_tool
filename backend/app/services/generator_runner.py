from __future__ import annotations

import asyncio
import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Sequence

from app.core.settings import settings


# Provider CLIs (notably the Claude CLI in `--print` mode) sometimes exit
# with returncode 0 even when the underlying request was rejected for
# usage-limit reasons — the limit message lands in stdout as plain text.
# Without explicit detection the runner treats those as successful empty
# runs, the file-existence check at publish-time then fails 14 minutes
# in. The patterns below are deliberately broad (rate limits, quota,
# context-window) so both Claude and Codex limit shapes are caught.
_USAGE_LIMIT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"you'?ve\s+hit\s+your\s+limit", re.IGNORECASE),
    re.compile(r"\busage\s+limit\b", re.IGNORECASE),
    # Standalone "rate limit" / "rate_limit_exceeded" — the boundary keeps
    # us from matching unrelated text that happens to contain the substring.
    # The optional suffix accepts whitespace, "_" or "-" as separator so
    # snake-case identifiers like `rate_limit_exceeded` are still caught.
    re.compile(
        r"\brate[\s_-]*limit(?:ed|[\s_-]+(?:exceeded|reached))?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bquota\s+exceeded\b", re.IGNORECASE),
    # HTTP 429 — require HTTP context or the "too many requests" suffix,
    # so the bare number 429 in payload data (e.g. "0429 W" in a heating
    # table) doesn't false-positive an entire task as a limit hit.
    re.compile(r"\b(?:HTTP|status(?:\s*code)?|error)\s*:?\s*429\b", re.IGNORECASE),
    re.compile(r"\b429\s+too\s+many\s+requests\b", re.IGNORECASE),
    # Claude CLI: "resets 10:50pm (UTC)" — gate on "limit" / "reset"
    # context to avoid matching arbitrary timestamps.
    re.compile(
        r"(?:limit|quota|usage).{0,80}?resets?\s+\d{1,2}[:.]?\d{0,2}\s*(?:am|pm)?\s*\(?utc",
        re.IGNORECASE | re.DOTALL,
    ),
)


def detect_usage_limit(stdout: str, stderr: str) -> str | None:
    """Return the offending line if a usage-limit marker is present, else None."""
    for stream in (stdout, stderr):
        if not stream:
            continue
        for line in stream.splitlines():
            for pattern in _USAGE_LIMIT_PATTERNS:
                if pattern.search(line):
                    return line.strip()
    return None


@dataclass(frozen=True)
class GenerationTask:
    """A single generation task produced by the planner.

    Each task targets one role-folder output file (or a small group of
    related files) and carries a self-contained prompt. Tasks marked
    ``final`` are executed only after every non-final task has finished
    so the navigation can reference the artefacts that already exist.
    """

    label: str
    folder: str
    files: tuple[str, ...]
    prompt: str
    final: bool = False
    depends_on_all_previous: bool = False


@dataclass
class TaskResult:
    task: GenerationTask
    returncode: int
    stdout: str
    stderr: str
    provider_name: str = ""
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None and self.returncode == 0


class LLMProvider(ABC):
    """Abstract LLM provider used by the generator."""

    name: str = "abstract"

    @abstractmethod
    def run(self, workspace_path: str, prompt: str) -> subprocess.CompletedProcess[str]:
        ...

    async def run_async(self, workspace_path: str, prompt: str) -> subprocess.CompletedProcess[str]:
        return await asyncio.to_thread(self.run, workspace_path, prompt)


class CodexProvider(LLMProvider):
    name = "codex"

    def __init__(self, profile: str | None = None, model: str | None = None, timeout: int | None = None) -> None:
        self.profile = profile or settings.codex_profile
        self.model = model if model is not None else settings.codex_model
        self.timeout = timeout if timeout is not None else settings.generator_task_timeout_seconds

    def build_command(self, workspace_path: str) -> list[str]:
        command: list[str] = [
            "codex",
            "exec",
            "-p",
            self.profile,
            "--cd",
            workspace_path,
            "--skip-git-repo-check",
            "-",
        ]
        if self.model:
            command[2:2] = ["-m", self.model]
        return command

    def run(self, workspace_path: str, prompt: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self.build_command(workspace_path),
            input=prompt,
            capture_output=True,
            text=True,
            check=False,
            timeout=self.timeout,
        )


_CLAUDE_DEFAULT_ALLOWED_TOOLS = "Read,Write,Edit,Glob,Grep,Bash,Task"


class ClaudeProvider(LLMProvider):
    name = "claude"

    def __init__(
        self,
        model: str | None = None,
        timeout: int | None = None,
        allowed_tools: str | None = None,
        max_turns: int | None = None,
    ) -> None:
        self.model = model if model is not None else settings.claude_model
        self.timeout = timeout if timeout is not None else settings.generator_task_timeout_seconds
        self.allowed_tools = allowed_tools or _CLAUDE_DEFAULT_ALLOWED_TOOLS
        self.max_turns = max_turns if max_turns is not None else 60

    def build_command(self) -> list[str]:
        command: list[str] = [
            "claude",
            "--print",
            "--output-format",
            "text",
            "--permission-mode",
            "acceptEdits",
            "--allowed-tools",
            self.allowed_tools,
            "--max-turns",
            str(self.max_turns),
        ]
        if self.model:
            command.extend(["--model", self.model])
        return command

    def run(self, workspace_path: str, prompt: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self.build_command(),
            input=prompt,
            capture_output=True,
            text=True,
            check=False,
            timeout=self.timeout,
            cwd=workspace_path,
        )


def get_provider(name: str | None = None) -> LLMProvider:
    """Single provider — first entry of the configured pool."""
    return get_provider_pool(name)[0]


def get_provider_pool(name: str | None = None) -> list[LLMProvider]:
    """Provider pool for round-robin task distribution.

    "codex" / "claude" -> single-element list with that provider.
    "both"             -> [CodexProvider, ClaudeProvider]; tasks rotate across them.
    """
    resolved = (name or settings.llm_provider or "both").strip().lower()
    if resolved == "codex":
        return [CodexProvider()]
    if resolved == "claude":
        return [ClaudeProvider()]
    if resolved in {"both", "mixed", "all"}:
        return [CodexProvider(), ClaudeProvider()]
    raise ValueError(f"Unknown LLM provider: {resolved}")


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


_BASE_RULES = """
<role>
Du erstellst SHK-Projektdokumentation (Sanitaer-Heizung-Klima) fuer
Heizungsmodernisierungen in Mehrfamilienhaeusern. Zielgruppe: Monteure
50+ auf der Baustelle mit Handschuhen und Smartphone, plus Buero-Rollen
(Bauleitung, Projektleitung). Ausgabe: in sich geschlossene HTML-Dateien,
die auf Mobil und als PDF gleichzeitig funktionieren.
</role>

<workspace>
- input.json           strukturierte, tokenisierte Projektdaten aus dem Formular
- heating_design.json  (optional) Heizlast pro Wohneinheit aus dem Heizlast-Import
                       (Felder: wohneinheit/etage/area_sqm/heat_load_w/volume_flow_lph/strand)
- offers.json          (optional) Angebote inkl. Lieferant, Items (Position/Artikel/
                       Menge/Einzelpreis/Gesamtpreis) und summary (offer_count, total_net_eur)
- docs/                tokenisierte technische Projektunterlagen
- privacy_manifest.json Hinweis zu tokenisierten/ausgeschlossenen Dateien
- voice_notes.json     (optional) Transkripte mit `intent`: ibn / uebergabe / daily_report / freitext
- photos.json          (optional) Foto-Metadaten pro Bauabschnitt/Tagesbericht
- photos/              (optional) Bilddateien, referenziert aus photos.json
- output/              Zielverzeichnis (rollenbasiert) — DEIN ALLEINIGER SCHREIBORT
</workspace>

<reference_schema path="{reference_schema_path}" />

<output_structure>
output/
  00_Start/         -> Navigation, NIE in regulaeren Tasks anfassen (eigener finaler Schritt)
  01_Monteur/       -> MONTEUR_*.html
  02_Obermonteur/   -> OBERMONTEUR_*.html
  03_Bauleitung/    -> BAULEITUNG_*.html
  04_Projektleitung/-> PROJEKTLEITUNG_*.html
  05_Allgemein/     -> ALLGEMEIN_*.html
</output_structure>

<safety_rules>
- Schreibe AUSSCHLIESSLICH in ./output/.
- Erzeuge jede Zieldatei nur als .html (keine .md-Doppel, keine anderen Suffixe).
- Verwende die exakte Datei- und Ordnerbenennung wie im Task vorgegeben.
- Bauabschnitte stammen AUSSCHLIESSLICH aus input.json (keine erfundene Anzahl).
- Fehlende Daten als "Offene Punkte" ausweisen — NIEMALS frei erfinden.
- Bewahre bestehende Dateien in ./output/, die nicht zum aktuellen Schritt gehoeren.
- Entferne keine Platzhalter wie [[PII:...]].
- Erzeuge keine Mail-only-Formulare und keine isolierten Mail-Endpunkte.
- Erzeuge keine externen Automations-Workflow-Dateien.
</safety_rules>

<style_contract>
Jede HTML-Datei beginnt mit Standard-Boilerplate:
- <!DOCTYPE html>, <html lang="de">, <head> mit <meta charset="utf-8">
- <meta name="viewport" content="width=device-width, initial-scale=1">
- <title> aussagekraeftig (z.B. "Tagescheckliste – Bauvorhaben XY")
- <style>-Block direkt im <head> mit allen drei CSS-Schichten unten

Print-CSS (PDF-Export geschieht on-the-fly):
- @page {{ size: A4; margin: 20mm; }}
- body {{ font-family: "DejaVu Sans", Arial, sans-serif; font-size: 11pt; line-height: 1.4; }}
- Tabellen: border-collapse: collapse, sichtbare 1px-Linien an th/td
- h1, h2, h3 {{ page-break-after: avoid; }}
- section, table, tr {{ page-break-inside: avoid; }}

Mobile-CSS (Baustelle, Smartphone, Handschuhe, Sonnenlicht):
- Body Default-Font min. 16px, auf Mobile 17-18px
- @media (max-width: 600px): font-size 17px, breite Tabellen scrollbar
  (overflow-x: auto) oder Spalten kollabieren (display: block pro tr)
- Hoher Kontrast: Text mindestens #1a1a1a auf #ffffff (AAA 7:1)
- Inputs: font-size: 16px (verhindert iOS-Auto-Zoom)

Tap-Target-Vertrag (kritisch fuer Handschuh-Bedienung):
- Alle interaktiven Elemente (input, button, select, [contenteditable]):
  min. 44x44 px Beruehrungsflaeche
- Primaere Aktionen (Bericht senden, Speichern): 56-64 px
- Checkboxen: width: 28px; height: 28px PLUS klickbares Label
  (label umschliesst die checkbox oder verweist via for=)
- Buttons IMMER mit Text + Icon, NIEMALS nur Icon
</style_contract>

<doc_type_badge>
Jede HTML-Datei beginnt im <body> mit GENAU einem Dokumenttyp-Badge:

Fuer ausfuellbare Dokumente (Checklisten, Protokolle, Berichte, Risiko-/Maengellisten, Formulare):
<div class="doc-type-badge fillable" style="display:inline-block; padding:6px 12px; border-radius:8px; background:#1769aa; color:#fff; font-weight:700; font-size:13px; margin:0 0 14px;">📋 Formular zum Ausfuellen</div>

Fuer rein informative Dokumente (Uebersichten, Gantt-Plaene, Stammdaten, Kontaktlisten, Navigation):
<div class="doc-type-badge info" style="display:inline-block; padding:6px 12px; border-radius:8px; background:#6c757d; color:#fff; font-weight:700; font-size:13px; margin:0 0 14px;">📄 Informativ</div>

Beide Badges im Print-CSS mit `display:none !important;` ausblenden (nicht im PDF sichtbar).
</doc_type_badge>

<field_id_contract>
JEDES ausfuellbare Element MUSS ein eindeutiges `data-field-id`-Attribut tragen.
Konvention:
  data-field-id="<role_folder_lower>.<doc_stem_lower>.<sektion>.<feld>"

Regeln:
- lowercase, Punkt-getrennt, ASCII (keine Umlaute, Sonderzeichen durch _ ersetzen)
- STABIL: bei jedem Re-Run identische IDs fuer identische Felder
- eindeutig pro Doku (keine Kollisionen)
- gilt fuer: <input type="checkbox|text|number|date">, <textarea>,
  <td contenteditable>, <select>
- Reine Anzeige-Tabellen (Gantt, Kontakte) tragen KEINE field_id
- Bei wiederholenden Sektionen (Abschnitt 1-4): `abschnitt_<N>` als Pfad-Segment
- Bei wiederholenden Tabellen-Zeilen: `r1`, `r2`, ... als Zeilen-Segment
</field_id_contract>

<cognitive_load_limits>
Die Dokumente werden auf der Baustelle unter Zeitdruck verwendet:
- Formulare mit >15 Checkboxen / Eingabefeldern MUESSEN in max. 3 Subsektionen
  mit eigener H3-Ueberschrift gruppiert werden
- Jede Subsektion logisch zusammenhaengend (z.B. "Tagesstart", "Laufende Arbeiten",
  "Tagesende") und max. 8-10 Eingaben pro Subsektion
- Labels in B1-Deutsch: kurz, imperativ, kein Fachjargon ohne Erklaerung
- Pflichtfelder markieren: rotes `*` direkt im Label PLUS `aria-required="true"` am Input
</cognitive_load_limits>

<protocol_layout>
Bauleitungs- und Protokoll-Dokumente (Uebergabe, Inbetriebnahme, Abnahme) folgen
deutscher Bau-Konvention nach BGB/BAuA/ZVSHK:
- Firmen-Briefkopf-Platzhalter oben links (Block vorsehen, leer ok)
- Bauvorhaben-Adresse oben rechts
- Datum-Zeile
- Unterschriftsfelder unten rechts (Auftraggeber/Auftragnehmer, je 200px breit)
- Footer: "Seite X von Y" via CSS counter-increment in @page
</protocol_layout>

<photo_embedding>
Wenn photos.json existiert, ist Foto-Einbettung PFLICHT (nicht optional):

- In BAULEITUNG_Detaillierter_Ablaufplan.html: pro Abschnitt (Feld section_number)
  eine Foto-Galerie mit ALLEN zugehoerigen Fotos. Hat ein Abschnitt keine Fotos:
  `<p class="empty-photos">Noch keine Fotos zu Abschnitt N.</p>`
- In BAULEITUNG_Risiken_und_Maengel.html: pro Mangel-Eintrag das relevante Foto,
  sofern eines mit passender section/daily_report_id existiert
- In jeder anderen Doku, die einen Bauabschnitt oder Tagesbericht referenziert:
  mind. ein repraesentatives Foto einbetten

Markup (relativ vom HTML aus):
  <figure>
    <img src="../photos/<filename>" alt="<caption>" loading="lazy">
    <figcaption>{{caption}}{{ – falls vorhanden: taken_at, GPS}}</figcaption>
  </figure>

- KEINE Fotos erfinden — nur was in photos.json aufgelistet ist
- Print-CSS: max-width: 100%; height: auto; page-break-inside: avoid;
- Mobile-CSS: Galerie als CSS-Grid `repeat(auto-fill, minmax(140px, 1fr))`
</photo_embedding>

<data_inputs>
voice_notes.json (optional): nach `intent` sortieren —
  - `ibn` -> IBN-Doku
  - `uebergabe` -> Uebergabeprotokoll
  - `daily_report` -> Tagesbericht-Kontext
  - `freitext` -> Hintergrundinfo fuer beliebige Dokumente
Das `transcript`-Feld ist das primaere Nutzsignal.
</data_inputs>

<subagent_strategy>
- Du darfst bis zu {subagent_limit} eigene Subagents PARALLEL starten, wenn die
  Aufgabe sauber zerlegbar ist (1 Subagent pro Bauabschnitt, pro Zieldatei,
  oder Recherche/Inhalt/Validierung getrennt)
- Jeder Subagent arbeitet im eigenen Kontextfenster und schreibt direkt in
  seine zugewiesene Datei innerhalb von ./output/
- Bei trivialen Tasks (1-2 kleine Dateien): kein Subagent, direkt arbeiten
- Subagents duerfen 00_Start/ NIE anfassen
</subagent_strategy>

<examples>
Diese 2 Beispiele zeigen die korrekten Patterns. Kopiere die Struktur (Boilerplate,
Badge, Style-Block, data-field-id-Vergabe), passe den Inhalt fuer deinen Task an.

<example type="fillable" filename="MONTEUR_Beispiel_Tagesstart.html">
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tagesstart – Beispiel</title>
  <style>
    body {{ font-family: "DejaVu Sans", Arial, sans-serif; font-size: 16px; line-height: 1.4; color: #1a1a1a; background: #fff; max-width: 760px; margin: 0 auto; padding: 16px; }}
    h1 {{ font-size: 24px; margin: 0 0 16px; }}
    h2 {{ font-size: 18px; margin: 24px 0 8px; }}
    label {{ display: flex; align-items: center; gap: 12px; padding: 10px 0; min-height: 44px; cursor: pointer; }}
    input[type="checkbox"] {{ width: 28px; height: 28px; flex-shrink: 0; }}
    input[type="text"] {{ font-size: 16px; min-height: 44px; padding: 8px 10px; width: 100%; box-sizing: border-box; }}
    .required {{ color: #b14040; }}
    @media (max-width: 600px) {{ body {{ font-size: 17px; }} }}
    @page {{ size: A4; margin: 20mm; }}
    @media print {{
      body {{ font-size: 11pt; }}
      .doc-type-badge {{ display: none !important; }}
      h1, h2, h3 {{ page-break-after: avoid; }}
      section {{ page-break-inside: avoid; }}
    }}
  </style>
</head>
<body>
  <div class="doc-type-badge fillable" style="display:inline-block; padding:6px 12px; border-radius:8px; background:#1769aa; color:#fff; font-weight:700; font-size:13px; margin:0 0 14px;">📋 Formular zum Ausfuellen</div>
  <h1>Tagesstart – Bauvorhaben [[PII:abc123:ADDRESS:0001]]</h1>
  <section>
    <h2>Persoenliche Schutzausruestung</h2>
    <label>
      <input type="checkbox" data-field-id="01_monteur.tagesstart.psa.helm">
      Helm getragen <span class="required" aria-hidden="true">*</span>
    </label>
    <label>
      <input type="checkbox" data-field-id="01_monteur.tagesstart.psa.handschuhe">
      Schutzhandschuhe griffbereit
    </label>
  </section>
  <section>
    <h2>Tageskoordination</h2>
    <label>
      Tagesziel mit Bauleitung abgestimmt
      <input type="text" data-field-id="01_monteur.tagesstart.koordination.tagesziel" aria-required="true">
    </label>
  </section>
</body>
</html>
</example>

<example type="info" filename="ALLGEMEIN_Beispiel_Kontakte.html">
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kontakte – Beispiel</title>
  <style>
    body {{ font-family: "DejaVu Sans", Arial, sans-serif; font-size: 16px; line-height: 1.4; color: #1a1a1a; background: #fff; max-width: 760px; margin: 0 auto; padding: 16px; }}
    h1 {{ font-size: 24px; margin: 0 0 16px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 12px; }}
    th, td {{ border: 1px solid #1a1a1a; padding: 10px; text-align: left; }}
    @media (max-width: 600px) {{
      body {{ font-size: 17px; }}
      table {{ display: block; overflow-x: auto; }}
    }}
    @page {{ size: A4; margin: 20mm; }}
    @media print {{
      body {{ font-size: 11pt; }}
      .doc-type-badge {{ display: none !important; }}
      table, tr {{ page-break-inside: avoid; }}
    }}
  </style>
</head>
<body>
  <div class="doc-type-badge info" style="display:inline-block; padding:6px 12px; border-radius:8px; background:#6c757d; color:#fff; font-weight:700; font-size:13px; margin:0 0 14px;">📄 Informativ</div>
  <h1>Projektkontakte</h1>
  <table>
    <thead><tr><th>Rolle</th><th>Person</th><th>Erreichbarkeit</th></tr></thead>
    <tbody>
      <tr><td>Bauleitung</td><td>[[PII:abc:PERSON:0001]]</td><td>Offen — bitte ergaenzen</td></tr>
      <tr><td>Obermonteur</td><td>[[PII:abc:PERSON:0002]]</td><td>Offen — bitte ergaenzen</td></tr>
    </tbody>
  </table>
</body>
</html>
</example>
</examples>
""".strip()


_NAV_HINT_NORMAL = (
    "Wichtig: Erzeuge in diesem Schritt KEINE 00_Start/index.html und KEINE "
    "00_Start/Projekt_Navigation.html. Diese werden ganz am Schluss in einem "
    "separaten Schritt erzeugt."
)

_NAV_HINT_FINAL = (
    "Wichtig: Dies ist der abschliessende Navigations-Schritt. Lies das "
    "vorhandene ./output/-Verzeichnis und verlinke ALLE vorhandenen Rollen-Ordner "
    "und ihre Dateien in 00_Start/Projekt_Navigation.html. 00_Start/index.html ist "
    "die Einstiegsseite (Projektname, Adresse, Rollenwahl, Verweis auf die "
    "Projekt_Navigation und auf die App-Bereiche)."
)


def _base_rules() -> str:
    """Stabiler System-Regel-Prefix.

    WICHTIG fuer Prompt-Caching: nichts Variables hier einbauen. Die
    Anthropic-API cached den Prompt-Prefix server-seitig fuer ~5 Minuten,
    wenn er bytegleich bleibt. Da alle 12-20 Subagent-Tasks pro Generator-
    Run innerhalb dieser Frist mit identischem Prefix laufen, sparen wir
    nach dem ersten Task ~90% Input-Token-Kosten auf den `_BASE_RULES`-
    Block — solange `extra_prompt` und sonstige variable Inhalte erst im
    task-spezifischen Teil (siehe `_task_prompt`) angehaengt werden.
    """
    return _BASE_RULES.format(
        reference_schema_path=settings.reference_schema_path,
        subagent_limit=settings.generator_subagent_limit,
    )


def _task_prompt(
    base_rules: str,
    folder: str,
    files: Sequence[str],
    purpose: str,
    final_navigation: bool = False,
    extra_prompt: str | None = None,
) -> str:
    file_list = "\n".join(f"- {folder}/{name}" for name in files)
    nav_hint = _NAV_HINT_FINAL if final_navigation else _NAV_HINT_NORMAL
    extra_block = (
        f"\n<extra_instruction>\n{extra_prompt.strip()}\n</extra_instruction>"
        if extra_prompt
        else ""
    )
    return f"""
{base_rules}

<task>
<folder>{folder}/</folder>
<purpose>{purpose}</purpose>
<files>
{file_list}
</files>
<nav_hint>{nav_hint}</nav_hint>
<missing_data_policy>
Wenn fachliche Daten fuer diese Dateien fehlen, dokumentiere die offenen
Punkte direkt in den erzeugten Dokumenten (Abschnitt "Offene Punkte").
</missing_data_policy>
{extra_block}
</task>

<final_checklist>
Bevor du den Task abschliesst, pruefe jedes Item fuer JEDE erzeugte Datei:
- [ ] Pfad exakt: ./output/{folder}/<dateiname>.html (kein .md, kein anderer Suffix)
- [ ] <!DOCTYPE html>, <html lang="de">, <meta charset="utf-8"> vorhanden
- [ ] <meta name="viewport" content="width=device-width, initial-scale=1"> vorhanden
- [ ] Aussagekraeftiger <title>
- [ ] GENAU ein doc-type-badge direkt im <body> (📋 fillable oder 📄 info)
- [ ] Print-CSS (@page A4, page-break-inside, badge display:none) im <style>-Block
- [ ] Mobile-CSS (@media max-width: 600px, font-size 17px, Tabellen scrollbar) im <style>-Block
- [ ] Alle interaktiven Elemente >= 44 px Tap-Target; Checkboxen 28 px + Label
- [ ] Inputs haben font-size: 16px (iOS-Auto-Zoom verhindert)
- [ ] Jedes ausfuellbare Element hat ein eindeutiges data-field-id im Format
      <role_folder_lower>.<doc_stem_lower>.<sektion>.<feld>
- [ ] Bei >15 Eingaben: in max. 3 Subsektionen mit H3 gruppiert
- [ ] Pflichtfelder mit rotem `*` UND aria-required="true" markiert
- [ ] Bei Protokollen: Briefkopf-Block, Bauvorhaben-Adresse, Datum, Unterschriften
- [ ] Bei photos.json + relevantem Bezug: Fotos eingebettet im <figure>-Markup
- [ ] PII-Token [[PII:...]] erhalten, NICHT entfernt oder umgeschrieben
- [ ] Kein erfundener Inhalt — fehlende Daten als "Offene Punkte" markiert
</final_checklist>
""".strip()


# ---------------------------------------------------------------------------
# Task planning
# ---------------------------------------------------------------------------


# Hinweis: Print-CSS-Vorgaben werden bewusst NICHT in `_BASE_RULES` aufgenommen,
# weil dort parallel der PDF-Export-Agent arbeitet. Stattdessen wird der
# Hinweis pro Pflicht-Doku-Task individuell mitgegeben, damit Doku-Tasks
# konsistent A4-tauglich rendern und der PDF-Service spaeter ohne weitere
# Anpassungen das HTML konvertieren kann.
_PRINT_CSS_HINT = (
    "\n\nPrint-Layout-Vorgaben fuer dieses Dokument (PDF-Export): A4-Format, "
    "20mm Seitenraender, font-size 11pt im Fliesstext. Tabellen und "
    "Sektionsbloecke bekommen `page-break-inside: avoid`, Ueberschriften "
    "`page-break-after: avoid`. Schreibe diese Regeln direkt in den "
    "`<style>`-Block der HTML-Datei (z.B. unter "
    "`@page { size: A4; margin: 20mm; }`). Innerhalb von @media print "
    "zusaetzlich `.doc-type-badge { display: none !important; }` setzen, "
    "damit das Dokumenttyp-Badge im PDF nicht auftaucht."
)


_HYDRAULIC_BALANCE_PURPOSE = (
    "VdZ-Verfahren-B-konforme Dokumentation des hydraulischen Abgleichs. "
    "Pflicht-Inhalt: "
    "(1) Anlagenkenndaten (System-Typ, Vorlauftemperatur, Ruecklauftemperatur, "
    "Spreizung, Gesamt-Volumenstrom). "
    "(2) Tabelle aller Heizkreise mit Spalten: Strang, Raum, "
    "Heizflaeche/Heizkreis, Heizlast [W], Volumenstrom [l/h], "
    "Voreinstellwert Ventil, kv-Wert, Rohrlaenge [m]. "
    "(3) Pumpe (Modell, Foerderhoehe in Pa, Differenzdruck). "
    "(4) Datum, Monteur, Unterschriften-Felder. "
    "(5) VdZ-Kompatibilitaetsvermerk in der Fusszeile. "
    "Datenquelle fuer die Heizkreis-Tabelle und Pumpenkennwerte: Verwende die "
    "Daten aus `heating_design.json` (liegt neben input.json im Workspace-Root). "
    "Wenn `heating_design.json` nicht existiert oder leer ist, weise dies "
    "unter 'Offene Punkte' aus und erzeuge nur die Anlagenkenndaten-Sektion "
    "mit leeren Platzhaltern fuer die Tabelle. Erfinde keine Heizkreis-Daten."
    + _PRINT_CSS_HINT
)


_COMMISSIONING_PROTOCOL_PURPOSE = (
    "Inbetriebnahmeprotokoll (IBN) gemaess SHK-Praxis. Pflicht-Inhalt: "
    "(1) Anlagenkenndaten (Hersteller, Typ, Seriennummer, Baujahr) — "
    "Felder bleiben fuer manuelle Eingabe leer, falls nicht in input.json "
    "vorhanden. "
    "(2) Sicherheitspruefung-Checkliste mit Haken-Boxen: "
    "Dichtheitspruefung, Abgaspruefung, Druckpruefung, Sicherheitsventil-Funktion. "
    "(3) Eingestellte Werte (Vorlauf-Temperatur in degC, Ruecklauf-Temperatur "
    "in degC, Anlagendruck in bar, Pumpenstufe) — soweit aus "
    "`heating_design.json` ableitbar, ansonsten leere Felder fuer manuelle "
    "Eingabe. "
    "(4) Einweisung-Kunde-Bestaetigungsfeld (Checkbox + Beschreibungstext). "
    "(5) Zwei Unterschriften-Boxen (jeweils ca. 60mm breit, 20mm hoch, "
    "gestrichelter Rahmen) mit den Beschriftungen 'Unterschrift Kunde' und "
    "'Unterschrift Monteur' — diese werden spaeter vom Signature-Pad gefuellt. "
    "(6) Datum, Ort."
    + _PRINT_CSS_HINT
)


_HANDOVER_PROTOCOL_PURPOSE = (
    "Uebergabe-/Abnahmeprotokoll nach BGB §640. Pflicht-Inhalt: "
    "(1) Leistungsbeschreibung — leite die durchgefuehrten Arbeiten aus den "
    "Bauabschnitten in input.json ab (kurze, klare Stichpunkte je Abschnitt). "
    "(2) Maengelliste / Restleistungen — Tabelle mit leeren Zeilen fuer "
    "manuelle Ergaenzung bei der Abnahme. "
    "(3) Vorbehalte — separater Abschnitt mit leeren Zeilen. "
    "(4) Datum der Abnahme mit klarem Hinweis 'Beginn der Gewaehrleistungsfrist "
    "gemaess BGB §634a'. "
    "(5) Zwei Unterschriften-Boxen mit den Beschriftungen 'Unterschrift Kunde' "
    "und 'Unterschrift Bauleitung'."
    + _PRINT_CSS_HINT
)


_KFW_FACHUNTERNEHMER_PURPOSE = (
    "KfW-Fachunternehmererklaerung gemaess KfW-Vordruck 152/430 (BEG-EM, "
    "Heizungstausch). Dieses Dokument ist Foerder-Nachweis und gleichzeitig "
    "ein zentrales Verkaufsargument gegenueber dem Endkunden. "
    "Pflicht-Inhalt: "
    "(1) Antragsteller-Block (Kunde): Name, Adresse, ggf. Telefon/E-Mail — "
    "Daten ausschliesslich aus input.json (Projekt-Stammdaten) ableiten. "
    "Wenn die Antragsteller-Daten in input.json unvollstaendig sind, weise "
    "die fehlenden Felder unter 'Offene Punkte' aus und setze Platzhalter "
    "in den Antragsteller-Block — niemals frei erfinden. "
    "(2) Fachunternehmen-Block (Stempel-Bereich): Firmenname, Anschrift, "
    "Eintragung Handwerksrolle. Diese Felder bleiben fuer manuelle Eingabe "
    "bzw. Firmenstempel LEER — setze deutlich erkennbare Platzhalter "
    "(z.B. '_________________' oder '[ Firmenstempel ]'). "
    "(3) Massnahmen-Beschreibung: Heizungs-Typ neu (z.B. Waermepumpe / "
    "Brennwert / Hybrid), Nennleistung in kW, energetische Mindestanforderungen "
    "gemaess BEG-EM-Anlage (z.B. JAZ >= 2,7 fuer Luft/Wasser-WP, eta_s >= "
    "Mindestwert). Soweit aus input.json ableitbar; sonst Platzhalter mit "
    "klarem Hinweis 'Bitte ergaenzen'. "
    "(4) Bestaetigung Mindestanforderungen erfuellt: Liste der zu "
    "bestaetigenden Punkte als Checkboxen oder Bestaetigungstext nach "
    "BEG-EM-Anlage (technische Mindestanforderungen Heizung). "
    "(5) Bestaetigung 'Hydraulischer Abgleich nach Verfahren B (VdZ) erfolgt' — "
    "verweist EXPLIZIT auf das Schwester-Dokument "
    "`BAULEITUNG_Hydraulischer_Abgleich.html` als Anhang/Nachweis. Diese "
    "Verkettung ist Pflicht, weil der hydraulische Abgleich KfW-foerderrelevant ist. "
    "(6) Datum, Ort, Unterschriften-Block: Firmenstempel-Feld + Unterschrift "
    "des Fachunternehmers (gestrichelter Rahmen, ca. 60mm x 20mm, "
    "Beschriftung 'Stempel und Unterschrift Fachunternehmer'). "
    "Fusszeile mit Hinweis auf KfW-Vordruck 152/430 und BEG-EM."
    + _PRINT_CSS_HINT
)


_RISK_ASSESSMENT_PURPOSE = (
    "Gefaehrdungsbeurteilung / SiGe-Plan fuer den SHK-Einsatz. Analysiere die "
    "Projektdaten in input.json (Bestandsanlage, Projektart, Bauabschnitte, "
    "Gebaeudealter wenn vorhanden) und identifiziere typische SHK-Risiken: "
    "Gasarbeiten, Heissarbeiten (Loeten, Schweissen), Asbest-Verdacht "
    "(Gebaeude vor 1993), Absturzgefahr (Dach, Leiter, Geruest), "
    "Elektroarbeiten, Staub- und Laermbelastung, enge Raeume/Kellergeschoss. "
    "Pflicht-Inhalt: "
    "(1) Tabelle 'Erkannte Risiken' mit Spalten: Risiko, Risiko-Stufe "
    "(gering/mittel/hoch), Auftreten in Bauabschnitt. "
    "(2) Tabelle 'Schutzmassnahmen' je Risiko mit Spalten: Risiko, "
    "Schutzmassnahme (PSA, Brandschutz/Feuerloescher, Lueftung, Absperrung, "
    "Sicherung gegen Absturz), Verantwortlicher. "
    "(3) Unterweisungs-Bestaetigungsfeld pro Mitarbeiter (Tabelle mit Spalten: "
    "Name, Datum Unterweisung, Unterschrift) — leere Zeilen fuer manuelle "
    "Eintraege. "
    "(4) Datum der Erstellung, Verantwortlicher (Bauleitung) mit "
    "Unterschriften-Feld. "
    "Wenn aus input.json kein Hinweis auf bestimmte Risiken hervorgeht, ziehe "
    "die fuer SHK-Heizungsbau typischen Standard-Risiken heran und markiere "
    "sie entsprechend."
    + _PRINT_CSS_HINT
)


# Per-Datei Purpose-Texte fuer die Rollen-Bulks. Ein eigener Task pro Datei
# erlaubt fokussierte Prompts (kleineres Kontextfenster -> weniger Context Rot,
# bessere Qualitaet) und echte Parallelitaet ueber alle Files hinweg.
_BULK_FILE_PURPOSES: dict[tuple[str, str], str] = {
    # 01_Monteur
    ("01_Monteur", "MONTEUR_Tagescheckliste.html"):
        "Tagescheckliste fuer den Monteur vor Ort: PSA, Tagesziel mit "
        "Bauleitung abstimmen, Sicherheits-Start (Strom/Wasser), pro "
        "Bauabschnitt aus input.json je 4-6 Hauptarbeiten als Checkbox, "
        "Tagesende (Werkzeug, Sauberkeit, Uebergabe). AUSFUELLBAR — alle "
        "Checkboxen mit data-field-id.",
    # MONTEUR_Wochenplan.html — entfernt. Wochenbericht entsteht automatisch
    # aus den Tagesberichten (App-getriggert oder via /weekly-reports/draft).
    ("01_Monteur", "MONTEUR_Ablaufplan_Abschnitte.html"):
        "Ablaufplan je Bauabschnitt aus input.json: wer macht was wann pro "
        "Abschnitt. INFORMATIV (keine data-field-id).",
    ("01_Monteur", "MONTEUR_Baustellenhinweise.html"):
        "Baustellen- und Sicherheitshinweise: Zufahrt, Lagerplatz, Sanitaer, "
        "Notruf, Verbote, Schluesselregelung, Hausordnung. Aus input.json "
        "rekonstruieren; fehlendes als 'Offener Punkt'. INFORMATIV.",
    # 02_Obermonteur
    ("02_Obermonteur", "OBERMONTEUR_Teamstatus.html"):
        "Teamstatus-Vorlage: Soll-/Ist-Stunden pro Person, Tagesstatus "
        "(gruen/gelb/rot), kurze Bemerkung. Tabelle mit contenteditable-"
        "Zellen und data-field-id pro Zelle. AUSFUELLBAR.",
    ("02_Obermonteur", "OBERMONTEUR_Abschnittsplanung.html"):
        "Abschnittsplanung auf Basis der Bauabschnitte aus input.json: "
        "Reihenfolge, Personalstaerke, Material, Fertigstellungstermin. "
        "AUSFUELLBAR.",
    ("02_Obermonteur", "OBERMONTEUR_Checklisten.html"):
        "Fachliche Checklisten pro Bauabschnitt: Hydraulik, Elektroanschluss, "
        "Daemmung, Pruefdruck. AUSFUELLBAR.",
    # 03_Bauleitung
    ("03_Bauleitung", "BAULEITUNG_Detaillierter_Ablaufplan.html"):
        "Detaillierter Bauablauf mit Gewerken und Meilensteinen pro "
        "Bauabschnitt. PFLICHT: pro Abschnitt eine Foto-Galerie aus "
        "photos.json (Feld section_number). INFORMATIV (keine data-field-id).",
    ("03_Bauleitung", "BAULEITUNG_Material_und_Werkzeug.html"):
        "Material- und Werkzeugliste pro Gewerk und Bauabschnitt — was ist "
        "da, was fehlt, was wird wann benoetigt. AUSFUELLBAR. "
        "Wenn offers.json existiert, übernimm die Positionen pro Angebot "
        "als Material-Grundlage: pro Angebot eine Sektion mit Lieferant, "
        "Angebots-Nr, Items (Position/Artikel/Menge/Einheitspreis/Gesamt) "
        "und einer Summenzeile. Bei mehreren Angeboten zeige sie "
        "untereinander mit Vergleichs-Summe am Ende.",
    ("03_Bauleitung", "BAULEITUNG_Risiken_und_Maengel.html"):
        "Risiken-/Maengelliste mit Schwere, Verantwortlichem, Frist. PFLICHT: "
        "pro Eintrag das relevante Foto aus photos.json einbetten, sofern "
        "vorhanden. AUSFUELLBAR.",
    ("03_Bauleitung", "BAULEITUNG_Blocker_und_Offene_Punkte.html"):
        "Offene Blocker und offene Punkte: was haengt, wer entscheidet, bis "
        "wann. AUSFUELLBAR.",
    # 04_Projektleitung
    ("04_Projektleitung", "PROJEKTLEITUNG_Projektuebersicht.html"):
        "Projektuebersicht: Bauvorhaben (Adresse, Bauherr), Stammdaten, "
        "Terminrahmen, Budget-Hochkant. INFORMATIV. "
        "Wenn heating_design.json vorhanden ist: Block 'Heizlast-Auslegung' "
        "mit Gesamt-Heizlast (Summe aller circuits.heat_load_w in kW), "
        "Anzahl Wohneinheiten, max Heizlast pro Wohnung und Hinweis auf "
        "Strang-Aufteilung. Wenn offers.json vorhanden ist: Block "
        "'Angebote' mit summary.offer_count, summary.total_net_eur und "
        "summary.suppliers.",
    ("04_Projektleitung", "PROJEKTLEITUNG_Meilensteinplan.html"):
        "Meilensteinplan mit Soll-/Ist-Terminen und Verantwortlichen je "
        "Meilenstein. AUSFUELLBAR (Ist-Termine, Status pro Meilenstein).",
    ("04_Projektleitung", "PROJEKTLEITUNG_Gantt_Uebersicht.html"):
        "Gantt-Uebersicht (Wochenraster) aller Bauabschnitte und Gewerke. "
        "REINE ANZEIGE — keine data-field-id. INFORMATIV.",
    ("04_Projektleitung", "PROJEKTLEITUNG_Statusuebersicht.html"):
        "Statusampel/-uebersicht je Bauabschnitt: gruen/gelb/rot mit kurzer "
        "Begruendung. AUSFUELLBAR (Status + Notiz pro Abschnitt).",
    # 05_Allgemein
    ("05_Allgemein", "ALLGEMEIN_Projektunterlagen.html"):
        "Beschreibung aller Projektunterlagen aus docs/: Dateiname, Inhalt, "
        "Quelle, letzter Stand. INFORMATIV.",
    ("05_Allgemein", "ALLGEMEIN_Kontakte.html"):
        "Kontaktliste aller Projektbeteiligten (Bauherr, Bauleitung, "
        "Obermonteur etc.). Bei fehlenden Telefon/E-Mail-Angaben: 'Offen — "
        "bitte ergaenzen'. INFORMATIV.",
    ("05_Allgemein", "ALLGEMEIN_Dokumentenindex.html"):
        "Tabellarischer Index ALLER erzeugten Dokumente nach Rolle, mit "
        "Direkt-Links auf die zugehoerigen HTML-Dateien. INFORMATIV.",
}


_ROLE_PREFIXES = (
    "MONTEUR_",
    "OBERMONTEUR_",
    "BAULEITUNG_",
    "PROJEKTLEITUNG_",
    "ALLGEMEIN_",
)


def _bulk_label(folder: str, filename: str) -> str:
    """Erzeugt ein Task-Label fuer eine Einzeldatei eines Rollen-Bulks.

    Beispiel: ("01_Monteur", "MONTEUR_Tagescheckliste.html") -> "01_Monteur_Tagescheckliste".
    Folgt der gleichen Konvention wie die Pflicht-Doku-Labels
    (z.B. "03_Bauleitung_Hydraulischer_Abgleich").
    """
    stem = filename.removesuffix(".html")
    for prefix in _ROLE_PREFIXES:
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
            break
    return f"{folder}_{stem}"


def _bulk_entry(folder: str, filename: str) -> tuple[str, str, tuple[str, ...], str]:
    """Plan-Eintrag fuer eine Bulk-Datei (ein Task = eine Datei)."""
    purpose = _BULK_FILE_PURPOSES[(folder, filename)]
    return (_bulk_label(folder, filename), folder, (filename,), purpose)


def _standard_tasks(base_rules: str, extra_prompt: str | None = None) -> list[GenerationTask]:
    # Bulk-Rollen-Dateien: ein Task pro Datei (siehe _bulk_entry).
    # Pflicht-Doku-Tasks sind bereits Einzel-File und folgen unten.
    plan: list[tuple[str, str, tuple[str, ...], str]] = [
        _bulk_entry("01_Monteur", "MONTEUR_Tagescheckliste.html"),
        # MONTEUR_Wochenplan entfernt — Wochenbericht entsteht aus Tagesberichten
        _bulk_entry("01_Monteur", "MONTEUR_Ablaufplan_Abschnitte.html"),
        _bulk_entry("01_Monteur", "MONTEUR_Baustellenhinweise.html"),
        _bulk_entry("02_Obermonteur", "OBERMONTEUR_Teamstatus.html"),
        _bulk_entry("02_Obermonteur", "OBERMONTEUR_Abschnittsplanung.html"),
        _bulk_entry("02_Obermonteur", "OBERMONTEUR_Checklisten.html"),
        _bulk_entry("03_Bauleitung", "BAULEITUNG_Detaillierter_Ablaufplan.html"),
        _bulk_entry("03_Bauleitung", "BAULEITUNG_Material_und_Werkzeug.html"),
        _bulk_entry("03_Bauleitung", "BAULEITUNG_Risiken_und_Maengel.html"),
        _bulk_entry("03_Bauleitung", "BAULEITUNG_Blocker_und_Offene_Punkte.html"),
        _bulk_entry("04_Projektleitung", "PROJEKTLEITUNG_Projektuebersicht.html"),
        _bulk_entry("04_Projektleitung", "PROJEKTLEITUNG_Meilensteinplan.html"),
        _bulk_entry("04_Projektleitung", "PROJEKTLEITUNG_Gantt_Uebersicht.html"),
        _bulk_entry("04_Projektleitung", "PROJEKTLEITUNG_Statusuebersicht.html"),
        _bulk_entry("05_Allgemein", "ALLGEMEIN_Projektunterlagen.html"),
        _bulk_entry("05_Allgemein", "ALLGEMEIN_Kontakte.html"),
        _bulk_entry("05_Allgemein", "ALLGEMEIN_Dokumentenindex.html"),
        # ----- Pflicht-Dokumentations-Tasks (IMPLEMENTIERUNGSPLAN_V2 10.2, 10.3, 10.5, 10.6) -----
        # Jedes Dokument bekommt einen eigenen Task, damit es parallel und mit
        # fachlich praezisem Prompt erzeugt werden kann. Zielordner sind die
        # bestehenden Rollen-Ordner; die Pflicht-Dateien stehen neben den
        # Standard-Outputs der jeweiligen Rolle.
        (
            "03_Bauleitung_Hydraulischer_Abgleich",
            "03_Bauleitung",
            ("BAULEITUNG_Hydraulischer_Abgleich.html",),
            _HYDRAULIC_BALANCE_PURPOSE,
        ),
        (
            "04_Projektleitung_Inbetriebnahmeprotokoll",
            "04_Projektleitung",
            ("PROJEKTLEITUNG_Inbetriebnahmeprotokoll.html",),
            _COMMISSIONING_PROTOCOL_PURPOSE,
        ),
        (
            "05_Allgemein_Uebergabeprotokoll",
            "05_Allgemein",
            ("ALLGEMEIN_Uebergabeprotokoll.html",),
            _HANDOVER_PROTOCOL_PURPOSE,
        ),
        (
            "03_Bauleitung_Gefaehrdungsbeurteilung",
            "03_Bauleitung",
            ("BAULEITUNG_Gefaehrdungsbeurteilung.html",),
            _RISK_ASSESSMENT_PURPOSE,
        ),
        # KfW-Fachunternehmererklaerung (IMPLEMENTIERUNGSPLAN_V2 10.4) —
        # Foerder-Nachweis BEG-EM, verkettet mit dem hydraulischen Abgleich.
        (
            "04_Projektleitung_KfW_Fachunternehmererklaerung",
            "04_Projektleitung",
            ("PROJEKTLEITUNG_KfW_Fachunternehmererklaerung.html",),
            _KFW_FACHUNTERNEHMER_PURPOSE,
        ),
    ]
    tasks = [
        GenerationTask(
            label=label,
            folder=folder,
            files=files,
            prompt=_task_prompt(
                base_rules, folder, files, purpose, extra_prompt=extra_prompt
            ),
        )
        for label, folder, files, purpose in plan
    ]
    # 00_Start (Navigation/Index) entfernt — die App-Sidebar übernimmt
    # Navigation, Subdomain ist abgeschaltet. War nur Redundanz.
    return tasks


def _small_tasks(
    base_rules: str,
    include_hydraulic_balance: bool = False,
    extra_prompt: str | None = None,
) -> list[GenerationTask]:
    plan: list[tuple[str, str, tuple[str, ...], str]] = [
        # Kleinprojekt-Bulk: ein Task pro Datei. Wochenplan, Obermonteur-
        # und Bauleitungs-Unterlagen entfallen bewusst (Aufwand vs. Nutzen).
        _bulk_entry("01_Monteur", "MONTEUR_Tagescheckliste.html"),
        _bulk_entry("01_Monteur", "MONTEUR_Ablaufplan_Abschnitte.html"),
        _bulk_entry("01_Monteur", "MONTEUR_Baustellenhinweise.html"),
        _bulk_entry("04_Projektleitung", "PROJEKTLEITUNG_Projektuebersicht.html"),
        _bulk_entry("04_Projektleitung", "PROJEKTLEITUNG_Meilensteinplan.html"),
        _bulk_entry("04_Projektleitung", "PROJEKTLEITUNG_Gantt_Uebersicht.html"),
        _bulk_entry("05_Allgemein", "ALLGEMEIN_Projektunterlagen.html"),
        _bulk_entry("05_Allgemein", "ALLGEMEIN_Kontakte.html"),
        # ----- Pflicht-Dokumente fuer Kleinprojekte -----
        # Kleinprojekte erhalten IBN- und Uebergabe-Protokoll, da beide auch
        # bei kleinen Auftraegen rechtlich/praktisch zwingend gebraucht werden.
        # Gefaehrdungsbeurteilung wird bei Mini-Projekten bewusst weggelassen
        # (Aufwand vs. Risiko-Profil) — kann manuell angefordert werden.
        (
            "04_Projektleitung_Inbetriebnahmeprotokoll",
            "04_Projektleitung",
            ("PROJEKTLEITUNG_Inbetriebnahmeprotokoll.html",),
            _COMMISSIONING_PROTOCOL_PURPOSE,
        ),
        (
            "05_Allgemein_Uebergabeprotokoll",
            "05_Allgemein",
            ("ALLGEMEIN_Uebergabeprotokoll.html",),
            _HANDOVER_PROTOCOL_PURPOSE,
        ),
        # KfW-Fachunternehmererklaerung auch bei Kleinprojekten zwingend —
        # Etagenheizung & Co. werden ebenfalls oft ueber KfW gefoerdert.
        (
            "04_Projektleitung_KfW_Fachunternehmererklaerung",
            "04_Projektleitung",
            ("PROJEKTLEITUNG_KfW_Fachunternehmererklaerung.html",),
            _KFW_FACHUNTERNEHMER_PURPOSE,
        ),
    ]
    if include_hydraulic_balance:
        plan.append(
            (
                "03_Bauleitung_Hydraulischer_Abgleich",
                "03_Bauleitung",
                ("BAULEITUNG_Hydraulischer_Abgleich.html",),
                _HYDRAULIC_BALANCE_PURPOSE,
            )
        )
    tasks = [
        GenerationTask(
            label=label,
            folder=folder,
            files=files,
            prompt=_task_prompt(
                base_rules, folder, files, purpose, extra_prompt=extra_prompt
            ),
        )
        for label, folder, files, purpose in plan
    ]
    # 00_Start entfernt — App-Sidebar navigiert, keine HTML-Navigation nötig.
    return tasks


def _navigation_task(
    base_rules: str,
    small: bool = False,
    extra_prompt: str | None = None,
) -> GenerationTask:
    folder = "00_Start"
    files = ("index.html", "Projekt_Navigation.html")
    purpose = (
        "Einstiegsseite und Dokumentennavigation. index.html zeigt Projektname, "
        "Adresse, Rolle-waehlen und Hauptaktionen. Projekt_Navigation.html ist "
        "die vollstaendige Liste aller erzeugten Dateien gruppiert nach Rollen-Ordnern."
    )
    if small:
        purpose += (
            " Hinweis Kleinprojekt: Es existieren nur die Ordner 00_Start, 01_Monteur, "
            "04_Projektleitung und 05_Allgemein."
        )
    return GenerationTask(
        label=folder,
        folder=folder,
        files=files,
        prompt=_task_prompt(
            base_rules,
            folder,
            files,
            purpose,
            final_navigation=True,
            extra_prompt=extra_prompt,
        ),
        final=True,
        depends_on_all_previous=True,
    )


def build_generation_tasks(
    project_type: str,
    section_count: int,
    extra_prompt: str | None = None,
    *,
    has_heating_design: bool = False,
) -> list[GenerationTask]:
    """Plan a parallelisable list of generation tasks for one project.

    ``has_heating_design`` steuert nur das Small-Projekt-Layout: ist es True,
    wird auch fuer Kleinprojekte der Hydraulische Abgleich (10.2) eingeplant.
    Standard-Projekte enthalten den Hydraulischen Abgleich immer; der Prompt
    selbst kommt mit fehlender `heating_design.json` zurecht und weist die
    fehlenden Daten als 'Offene Punkte' aus.
    """
    base_rules = _base_rules()
    if project_type == "small":
        return _small_tasks(
            base_rules,
            include_hydraulic_balance=has_heating_design,
            extra_prompt=extra_prompt,
        )
    return _standard_tasks(base_rules, extra_prompt=extra_prompt)


def build_overall_prompt(project_type: str, extra_prompt: str | None = None) -> str:
    """Single prompt rendered for dry-runs / preview purposes."""
    base_rules = _base_rules()
    tasks = build_generation_tasks(project_type, 0, extra_prompt)
    targets = "\n".join(f"- {task.folder}: {', '.join(task.files)}" for task in tasks)
    extra_block = (
        f"\n\nZusaetzliche Anweisung fuer diesen Lauf:\n{extra_prompt.strip()}"
        if extra_prompt
        else ""
    )
    return f"""
{base_rules}

Geplante Tasks (werden parallel ausgefuehrt, Navigation am Schluss):
{targets}{extra_block}
""".strip()


# ---------------------------------------------------------------------------
# Parallel execution
# ---------------------------------------------------------------------------


ProgressCallback = Callable[[list[str], int, int], Awaitable[None]]


@dataclass
class GenerationOutcome:
    results: list[TaskResult] = field(default_factory=list)
    failed_tasks: list[str] = field(default_factory=list)

    @property
    def has_failures(self) -> bool:
        return bool(self.failed_tasks)

    def combined_stdout(self) -> str:
        return "\n\n".join(
            f"===== {result.task.label} [{result.provider_name or 'unknown'}] =====\n{result.stdout}"
            for result in self.results
        )

    def combined_stderr(self) -> str:
        return "\n\n".join(
            f"===== {result.task.label} [{result.provider_name or 'unknown'}] =====\n{result.stderr}"
            for result in self.results
        )

    def provider_breakdown(self) -> dict[str, int]:
        """How many tasks ran on each provider — useful for run summaries."""
        counts: dict[str, int] = {}
        for result in self.results:
            key = result.provider_name or "unknown"
            counts[key] = counts.get(key, 0) + 1
        return counts


async def run_generation_tasks(
    workspace_path: str,
    tasks: Sequence[GenerationTask],
    provider: LLMProvider | Sequence[LLMProvider],
    parallelism: int | None = None,
    progress: ProgressCallback | None = None,
) -> GenerationOutcome:
    """Execute generation tasks. Non-final tasks run in parallel,
    final tasks (e.g. navigation) run sequentially afterwards.

    ``provider`` may be a single ``LLMProvider`` or a list of providers; in the
    latter case tasks are distributed round-robin across the pool so both
    Codex and Claude can be used within the same generation run.
    """

    providers: list[LLMProvider] = list(provider) if isinstance(provider, (list, tuple)) else [provider]
    if not providers:
        raise ValueError("At least one provider is required")

    concurrency = max(1, parallelism if parallelism is not None else settings.generator_parallelism)
    outcome = GenerationOutcome()
    total = len(tasks)

    parallel_tasks = [task for task in tasks if not task.final]
    final_tasks = [task for task in tasks if task.final]

    completed = 0
    running: dict[str, GenerationTask] = {}
    state_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(concurrency)

    async def emit_progress() -> None:
        if progress is None:
            return
        await progress(sorted(running.keys()), completed, total)

    async def run_one(task: GenerationTask, assigned_provider: LLMProvider) -> TaskResult:
        nonlocal completed
        async with semaphore:
            async with state_lock:
                running[task.label] = task
            await emit_progress()
            try:
                process = await assigned_provider.run_async(workspace_path, task.prompt)
                stdout_text = process.stdout or ""
                stderr_text = process.stderr or ""
                limit_hit = detect_usage_limit(stdout_text, stderr_text)
                if limit_hit:
                    # Force failure even if the CLI exited with code 0 —
                    # without this the empty output is treated as success.
                    result = TaskResult(
                        task=task,
                        returncode=process.returncode if process.returncode else 1,
                        stdout=stdout_text,
                        stderr=stderr_text,
                        error=f"Usage limit erreicht ({assigned_provider.name}): {limit_hit}",
                        provider_name=assigned_provider.name,
                    )
                else:
                    result = TaskResult(
                        task=task,
                        returncode=process.returncode,
                        stdout=stdout_text,
                        stderr=stderr_text,
                        provider_name=assigned_provider.name,
                    )
            except Exception as exc:
                result = TaskResult(
                    task=task,
                    returncode=1,
                    stdout="",
                    stderr=str(exc),
                    error=str(exc),
                    provider_name=assigned_provider.name,
                )
            async with state_lock:
                running.pop(task.label, None)
                completed += 1
            await emit_progress()
            return result

    if parallel_tasks:
        parallel_results = await asyncio.gather(
            *(
                run_one(task, providers[index % len(providers)])
                for index, task in enumerate(parallel_tasks)
            )
        )
        outcome.results.extend(parallel_results)
        for result in parallel_results:
            if not result.succeeded:
                outcome.failed_tasks.append(result.task.label)

    for index, task in enumerate(final_tasks):
        result = await run_one(task, providers[index % len(providers)])
        outcome.results.append(result)
        if not result.succeeded:
            outcome.failed_tasks.append(result.task.label)

    return outcome
