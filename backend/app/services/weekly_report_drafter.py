"""Smart drafting of weekly reports.

Aggregates the daily reports of a week, asks an LLM provider to produce a
structured summary, and returns a ``WeeklyReportDraft`` that the frontend
can pre-fill into the weekly-report form. The draft is *not* persisted —
the user always reviews and explicitly saves the final report.

The LLM call is asynchronous (the provider's ``run_async`` method runs the
underlying ``subprocess`` in a worker thread via ``asyncio.to_thread``), so
the request handler stays non-blocking even though the underlying CLIs are
synchronous binaries.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date
from tempfile import TemporaryDirectory
from typing import Sequence

from sqlalchemy.orm import Session

from app.db.orm_models import DailyReport, Project
from app.services.generator_runner import LLMProvider, get_provider_pool

logger = logging.getLogger(__name__)


_NO_DAILY_HINT = (
    "Keine Tagesberichte in dieser Woche erfasst — Wochenbericht muss manuell "
    "befüllt werden."
)


@dataclass
class WeeklyReportDraft:
    summary: str
    next_week_plan: str
    manpower_notes: str
    material_notes: str
    risks: str
    status: str  # "green" | "yellow" | "red"


def _derive_status(reports: Sequence[DailyReport]) -> str:
    """Heuristic: any red -> red, otherwise any yellow -> yellow, else green."""
    has_red = any(r.status == "red" for r in reports)
    if has_red:
        return "red"
    has_yellow = any(r.status == "yellow" for r in reports)
    if has_yellow:
        return "yellow"
    return "green"


def build_deterministic_draft(
    reports: Sequence[DailyReport],
) -> WeeklyReportDraft:
    """Build a draft WITHOUT calling an LLM — pure aggregation.

    Fast (< 10 ms), free, always available. The frontend can offer this as
    the default "Entwurf aus Tagesberichten" and let the user optionally
    request an LLM-polished version on top.
    """
    if not reports:
        return WeeklyReportDraft(
            summary=_NO_DAILY_HINT,
            next_week_plan="",
            manpower_notes="",
            material_notes="",
            risks="",
            status="green",
        )

    def _author(r) -> str:
        """Author-Hinweis pro Tagesbericht: '[Name]' oder leerer String."""
        try:
            if r.user is not None:
                name = r.user.display_name or r.user.username
                if name:
                    return f" [{name}]"
        except Exception:
            pass
        return ""

    def _collect(attr: str) -> list[str]:
        out: list[str] = []
        for r in reports:
            v = getattr(r, attr, None)
            if v and str(v).strip():
                # Prefix mit Datum + Autor, damit Bauleitung sofort sieht:
                # wer hat was wann gemeldet.
                out.append(f"• {r.report_date.isoformat()}{_author(r)}: {str(v).strip()}")
        return out

    def _unique(attr: str) -> list[str]:
        seen: list[str] = []
        for r in reports:
            v = getattr(r, attr, None)
            if not v:
                continue
            text = str(v).strip()
            if text and text not in seen:
                seen.append(text)
        return seen

    # Beteiligte Monteure (für manpower_notes)
    authors_set: list[str] = []
    for r in reports:
        try:
            if r.user is not None:
                name = r.user.display_name or r.user.username
                if name and name not in authors_set:
                    authors_set.append(name)
        except Exception:
            pass

    completed = _collect("completed_work")
    open_work = _collect("open_work")
    material = _collect("material_missing")
    blockers = _collect("blockers")
    teams = _unique("team")
    days_red = [r.report_date.isoformat() for r in reports if r.status == "red"]
    days_yellow = [r.report_date.isoformat() for r in reports if r.status == "yellow"]

    # Stunden-Summe und pro-Autor-Aufstellung (wenn ist_hours erfasst)
    hours_by_author: dict[str, float] = {}
    for r in reports:
        h = getattr(r, "ist_hours", None) or 0
        if h <= 0:
            continue
        try:
            name = (r.user.display_name or r.user.username) if r.user else "Unbekannt"
        except Exception:
            name = "Unbekannt"
        hours_by_author[name] = hours_by_author.get(name, 0.0) + float(h)

    summary_parts: list[str] = [
        f"Woche mit {len(reports)} Tagesbericht(en) von {len(authors_set)} Monteur(en) erfasst.",
    ]
    if authors_set:
        summary_parts.append(f"Beteiligte: {', '.join(authors_set)}.")
    if days_red:
        summary_parts.append(f"Rot-Tage: {', '.join(days_red)}.")
    if days_yellow:
        summary_parts.append(f"Gelb-Tage: {', '.join(days_yellow)}.")
    if completed:
        summary_parts.append("Erledigt diese Woche:")
        summary_parts.extend(completed)
    summary = "\n".join(summary_parts)

    # manpower_notes baut sich aus Stunden pro Monteur + Team-Einträgen
    manpower_lines: list[str] = []
    if hours_by_author:
        total_h = sum(hours_by_author.values())
        manpower_lines.append(f"Gesamt-Stunden: {total_h:.1f} h")
        for name, h in sorted(hours_by_author.items(), key=lambda kv: -kv[1]):
            manpower_lines.append(f"• {name}: {h:.1f} h")
    if teams:
        manpower_lines.append("Team-Einträge: " + ", ".join(teams))

    return WeeklyReportDraft(
        summary=summary,
        next_week_plan="\n".join(open_work) if open_work
            else "Keine offenen Arbeiten aus den Tagesberichten markiert.",
        manpower_notes="\n".join(manpower_lines) if manpower_lines else "",
        material_notes="\n".join(material) if material else "",
        risks="\n".join(blockers) if blockers else "",
        status=_derive_status(reports),
    )


def _format_daily_reports(reports: Sequence[DailyReport]) -> str:
    """Render the daily reports as a compact Markdown table-ish block for the prompt."""
    lines: list[str] = []
    for report in reports:
        lines.append(f"## {report.report_date.isoformat()} — Status: {report.status}")
        section = report.section_number if report.section_number is not None else "—"
        lines.append(f"- Abschnitt: {section}")
        if report.team:
            lines.append(f"- Team: {report.team}")
        if report.completed_work:
            lines.append(f"- Erledigt: {report.completed_work}")
        if report.open_work:
            lines.append(f"- Offen: {report.open_work}")
        if report.material_missing:
            lines.append(f"- Material fehlt: {report.material_missing}")
        if report.blockers:
            lines.append(f"- Blocker: {report.blockers}")
        if report.notes:
            lines.append(f"- Notizen: {report.notes}")
        lines.append("")
    return "\n".join(lines).strip()


def _build_prompt(
    project: Project,
    week_start: date,
    week_end: date,
    reports: Sequence[DailyReport],
) -> str:
    daily_block = _format_daily_reports(reports)
    return f"""
Du bist ein Bauleitungs-Assistent und verdichtest die Tagesberichte einer
Kalenderwoche zu einem Wochenbericht-Entwurf.

Projekt: {project.name} ({project.slug})
Woche: {week_start.isoformat()} bis {week_end.isoformat()}

Tagesberichte dieser Woche:
{daily_block}

Aufgabe: Erzeuge einen kurzen, sachlichen Wochenbericht-Entwurf mit genau
diesen Feldern:
- "summary": 3-6 Sätze, was wurde diese Woche geschafft, wo stehen wir.
- "next_week_plan": 2-4 Stichpunkte für die nächste Woche.
- "manpower_notes": Hinweise zu Personal/Team (kurz, ggf. leer).
- "material_notes": Hinweise zu Material/Engpässen (kurz, ggf. leer).
- "risks": Risiken und Blocker für die Projektleitung (kurz, ggf. leer).

WICHTIG: Antworte AUSSCHLIESSLICH mit einem gültigen JSON-Objekt, ohne
Markdown-Codefence, ohne erläuternden Text drumherum. Beispiel-Form:

{{"summary": "...", "next_week_plan": "...", "manpower_notes": "...", "material_notes": "...", "risks": "..."}}
""".strip()


_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def _extract_json(raw: str) -> dict[str, object] | None:
    """Try to parse the LLM output as JSON. Falls back to searching for a JSON
    object inside the text (in case the model wrapped it in code fences)."""
    candidate = raw.strip()
    # Strip common code-fence wrappers.
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        # Remove an optional language tag like ``json\n`` at the very start.
        if "\n" in candidate:
            first_line, rest = candidate.split("\n", 1)
            if first_line.strip().lower() in {"json", ""}:
                candidate = rest
    try:
        data = json.loads(candidate)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    match = _JSON_OBJECT_RE.search(raw)
    if match is None:
        return None
    try:
        data = json.loads(match.group(0))
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        return None
    return None


def _empty_draft(status: str = "green", summary: str = "") -> WeeklyReportDraft:
    return WeeklyReportDraft(
        summary=summary,
        next_week_plan="",
        manpower_notes="",
        material_notes="",
        risks="",
        status=status,
    )


async def draft_weekly_report(
    db: Session,
    project: Project,
    week_start: date,
    week_end: date,
    *,
    provider: LLMProvider | None = None,
) -> WeeklyReportDraft:
    """Aggregate daily reports of a week and ask an LLM for a structured draft.

    Returns a draft with the five free-text fields plus an auto-derived
    ``status``. The draft is never persisted; the caller hands it to the
    frontend which the user then edits and posts via the normal
    ``POST /weekly-reports`` endpoint.

    ``provider`` is optional and exists for tests/dependency injection.
    Production code uses ``get_provider_pool()[0]`` (Codex first, Claude as
    fallback when the pool is configured for "both").
    """
    reports: list[DailyReport] = (
        db.query(DailyReport)
        .filter(
            DailyReport.project_id == project.id,
            DailyReport.report_date >= week_start,
            DailyReport.report_date <= week_end,
        )
        .order_by(DailyReport.report_date.asc(), DailyReport.created_at.asc())
        .all()
    )

    if not reports:
        return _empty_draft(status="green", summary=_NO_DAILY_HINT)

    status = _derive_status(reports)
    prompt = _build_prompt(project, week_start, week_end, reports)

    used_provider = provider if provider is not None else get_provider_pool()[0]

    # Most providers (Codex) require a workspace path. The drafter has no
    # workspace of its own; a short-lived temp directory is enough.
    with TemporaryDirectory(prefix="weekly_draft_") as tmpdir:
        try:
            process = await used_provider.run_async(tmpdir, prompt)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Weekly draft provider call failed: %s", exc)
            return _empty_draft(
                status=status,
                summary=f"Automatischer Entwurf nicht möglich: {exc}",
            )

    raw = (process.stdout or "").strip()
    if process.returncode != 0 or not raw:
        stderr = (process.stderr or "").strip()
        logger.warning(
            "Weekly draft provider returned non-zero (%s); stderr=%r",
            process.returncode,
            stderr[:300],
        )
        return _empty_draft(
            status=status,
            summary=raw or "Automatischer Entwurf nicht möglich (keine Antwort vom LLM).",
        )

    parsed = _extract_json(raw)
    if parsed is None:
        logger.warning(
            "Weekly draft: provider response was not valid JSON, falling back to raw text."
        )
        return WeeklyReportDraft(
            summary=raw,
            next_week_plan="",
            manpower_notes="",
            material_notes="",
            risks="",
            status=status,
        )

    return WeeklyReportDraft(
        summary=str(parsed.get("summary", "") or ""),
        next_week_plan=str(parsed.get("next_week_plan", "") or ""),
        manpower_notes=str(parsed.get("manpower_notes", "") or ""),
        material_notes=str(parsed.get("material_notes", "") or ""),
        risks=str(parsed.get("risks", "") or ""),
        status=status,
    )
