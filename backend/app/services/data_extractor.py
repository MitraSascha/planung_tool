"""Domain-aware data extractor — replaces the old "Codex writes 25 HTMLs"
flow with "Codex extracts JSON, templates render".

The orchestrator runs one LLM call per domain (project stammdaten +
sections, personnel, risks/defects, material/tooling) against the
domain-relevant source slices (briefing, offer-PDFs, voicenote
transcripts, free-text uploads). Each call returns strict JSON validated
against a Pydantic schema and then upserted into the existing ORM tables.

Heating-design data is intentionally NOT extracted by the LLM here — that
domain has its own deterministic Excel/CSV importer that we trigger
automatically when a candidate file is among the uploads.

Source-routing per domain (best-practice, LangChain-style):

  project_meta + sections   <- briefing.md, voicenotes
  personnel                 <- briefing.md
  risks                     <- briefing.md, voicenotes
  material                  <- briefing.md, offer-PDFs (ANG-*)
  hydraulics                <- excel/csv via heating_importers (no LLM)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.db.orm_models import (
    HeatingDesign,
    MaterialItem,
    Project,
    ProjectMember,
    ProjectSection,
    ProjectUpload,
    RiskIssue,
    SectionSchedule,
    User,
    VoiceNote,
)
from app.services.generator_runner import LLMProvider


# ───────────────────────────────────────────────────────────────────────────
# Schemas — what the LLM is contracted to produce per domain
# ───────────────────────────────────────────────────────────────────────────


class SectionExtract(BaseModel):
    number: int
    name: str
    goal: str | None = None
    planned_hours: float | None = None
    responsible: str | None = None
    staff: str | None = None
    start_date: _date | None = None
    end_date: _date | None = None


class ProjectStamm(BaseModel):
    address: str | None = None
    auftraggeber: str | None = None
    responsible: str | None = None
    construction_manager: str | None = None
    foreman: str | None = None
    planned_start: _date | None = None
    planned_end: _date | None = None
    project_type: str | None = None
    sections: list[SectionExtract] = Field(default_factory=list)


class PersonExtract(BaseModel):
    name: str
    role: Literal["projektleitung", "bauleitung", "obermonteur", "monteur", "external"] = "monteur"
    phone: str | None = None
    email: str | None = None


class PersonnelExtract(BaseModel):
    persons: list[PersonExtract] = Field(default_factory=list)


class RiskExtract(BaseModel):
    section_number: int | None = None
    kind: Literal["risiko", "mangel"] = "risiko"
    description: str
    severity: Literal["hoch", "mittel", "gering"] = "mittel"
    responsible: str | None = None
    due_date: _date | None = None


class RisksExtract(BaseModel):
    risks: list[RiskExtract] = Field(default_factory=list)


class MaterialExtract(BaseModel):
    section_number: int | None = None
    kind: Literal["material", "werkzeug"] = "material"
    name: str
    soll_qty: float | None = None
    unit: str | None = None
    note: str | None = None


class MaterialList(BaseModel):
    items: list[MaterialExtract] = Field(default_factory=list)


# ───────────────────────────────────────────────────────────────────────────
# Source loaders — collect text for each domain
# ───────────────────────────────────────────────────────────────────────────


@dataclass
class SourceBundle:
    briefing: str
    voicenotes: str
    offer_texts: str
    other_uploads: str

    def __str__(self) -> str:
        parts = []
        if self.briefing.strip():
            parts.append(f"<briefing>\n{self.briefing}\n</briefing>")
        if self.voicenotes.strip():
            parts.append(f"<voicenotes>\n{self.voicenotes}\n</voicenotes>")
        if self.offer_texts.strip():
            parts.append(f"<offers>\n{self.offer_texts}\n</offers>")
        if self.other_uploads.strip():
            parts.append(f"<other_uploads>\n{self.other_uploads}\n</other_uploads>")
        return "\n\n".join(parts) or "(keine Quelldaten vorhanden)"


def _read_text_file(path: Path, max_chars: int = 50_000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return f"(Fehler beim Lesen {path.name}: {exc})"
    if len(text) > max_chars:
        return text[:max_chars] + "\n[... truncated]"
    return text


def _read_pdf_text(path: Path, max_chars: int = 60_000) -> str:
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        chunks: list[str] = []
        for page in reader.pages:
            chunks.append(page.extract_text() or "")
        text = "\n".join(chunks)
    except Exception as exc:  # noqa: BLE001
        return f"(Fehler beim Lesen {path.name}: {exc})"
    if len(text) > max_chars:
        return text[:max_chars] + "\n[... truncated]"
    return text


def load_sources(sanitized_root: Path) -> SourceBundle:
    """Collect text source material exclusively from the **sanitized**
    generator workspace produced by ``prepare_sanitized_generator_workspace``.

    Critical: **never** read from ``ProjectUpload.path`` or
    ``VoiceNote.transcript`` directly — those are the un-tokenized
    originals. The privacy pipeline writes tokenized copies into
    ``<sanitized_root>/{input.json, voice_notes.json, docs/}`` and that
    directory is the only thing the LLM ever sees.
    """
    # Project stammdaten — input.json is the canonical structured briefing.
    input_path = sanitized_root / "input.json"
    briefing = _read_text_file(input_path) if input_path.exists() else ""

    # Voicenote transcripts — already tokenized via privacy_workspace.
    voicenotes_path = sanitized_root / "voice_notes.json"
    voicenotes = _read_text_file(voicenotes_path) if voicenotes_path.exists() else ""

    # PDFs and Excels are pre-extracted to .txt under generator_input/docs/.
    docs_dir = sanitized_root / "docs"
    offer_chunks: list[str] = []
    other_chunks: list[str] = []
    if docs_dir.exists():
        for source_file in sorted(docs_dir.rglob("*")):
            if not source_file.is_file():
                continue
            name = source_file.name
            if name.endswith(".txt") or source_file.suffix.lower() in {".md", ".csv", ".json", ".html", ".txt"}:
                chunk = f"--- {name} ---\n{_read_text_file(source_file)}"
                if "ANG-" in name.upper() or name.lower().startswith("ang"):
                    offer_chunks.append(chunk)
                else:
                    other_chunks.append(chunk)

    return SourceBundle(
        briefing=briefing,
        voicenotes=voicenotes,
        offer_texts="\n\n".join(offer_chunks),
        other_uploads="\n\n".join(other_chunks),
    )


# ───────────────────────────────────────────────────────────────────────────
# LLM call + JSON parsing
# ───────────────────────────────────────────────────────────────────────────


class ExtractionError(RuntimeError):
    pass


_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _call_llm_json(
    provider: LLMProvider,
    workspace_path: str,
    domain_label: str,
    schema_model: type[BaseModel],
    source_text: str,
    domain_instructions: str,
):
    """Generic per-domain LLM call. Builds a JSON-only prompt, calls the
    provider, parses the response into ``schema_model``."""
    schema_json = json.dumps(schema_model.model_json_schema(), ensure_ascii=False, indent=2)
    prompt = (
        f"Du bist Daten-Extraktor für ein Heizungs-Sanierungsprojekt "
        f"der Mitra Sanitär GmbH (Domäne: {domain_label}).\n\n"
        f"AUFGABE: {domain_instructions}\n\n"
        f"REGELN:\n"
        f"- Antwort ist **ausschließlich** gültiges JSON nach dem unten gezeigten Schema.\n"
        f"- Kein Markdown, keine Erklärungen davor oder danach.\n"
        f"- Datumsformat ISO (YYYY-MM-DD).\n"
        f"- Wenn ein Feld nicht in den Quelldaten vorkommt: weglassen.\n"
        f"- Sprache des Inhalts: Deutsch. Personennamen genau wie in der Quelle.\n\n"
        f"SCHEMA:\n{schema_json}\n\n"
        f"QUELLDATEN:\n{source_text}\n\n"
        f"JSON-ANTWORT:"
    )
    completed = provider.run(workspace_path, prompt)
    if completed.returncode != 0:
        raise ExtractionError(
            f"[{domain_label}] LLM exit {completed.returncode}: {(completed.stderr or '')[:400]}"
        )
    raw = (completed.stdout or "").strip()
    raw = _JSON_FENCE_RE.sub("", raw).strip()
    # Codex sometimes prefixes its answer; pull the first {...} block.
    if not raw.startswith("{"):
        first_brace = raw.find("{")
        if first_brace >= 0:
            raw = raw[first_brace:]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"[{domain_label}] invalid JSON: {exc}; head={raw[:300]!r}") from exc
    try:
        return schema_model.model_validate(data)
    except ValidationError as exc:
        raise ExtractionError(f"[{domain_label}] schema mismatch: {exc}") from exc


# ───────────────────────────────────────────────────────────────────────────
# Domain extractors
# ───────────────────────────────────────────────────────────────────────────


def extract_project_stamm(provider, workspace_path, sources: SourceBundle) -> ProjectStamm:
    return _call_llm_json(
        provider,
        workspace_path,
        domain_label="Projekt-Stammdaten + Bauabschnitte",
        schema_model=ProjectStamm,
        source_text=f"{sources.briefing}\n\n{sources.voicenotes}",
        domain_instructions=(
            "Extrahiere die Projektstammdaten (Adresse, Auftraggeber, Verantwortliche, "
            "Projekt-Start/Ende) und die Bauabschnitte (Nummer, Name, Ziel, geplante Stunden, "
            "verantwortliche Person, eingesetztes Personal, ggf. Start-/Endtermine). "
            "Wenn keine Termine pro Abschnitt vorgegeben sind: Felder weglassen."
        ),
    )


def extract_personnel(provider, workspace_path, sources: SourceBundle) -> PersonnelExtract:
    return _call_llm_json(
        provider,
        workspace_path,
        domain_label="Personen + Rollen",
        schema_model=PersonnelExtract,
        source_text=sources.briefing,
        domain_instructions=(
            "Liste alle im Projekt vorkommenden Personen mit ihrer projektbezogenen Rolle. "
            "Rollen sind: projektleitung, bauleitung, obermonteur, monteur, external. "
            "Telefon und E-Mail nur eintragen, wenn explizit angegeben."
        ),
    )


def extract_risks(provider, workspace_path, sources: SourceBundle) -> RisksExtract:
    return _call_llm_json(
        provider,
        workspace_path,
        domain_label="Risiken + Mängel",
        schema_model=RisksExtract,
        source_text=f"{sources.briefing}\n\n{sources.voicenotes}",
        domain_instructions=(
            "Erfasse Risiken (präventiv) und Mängel (reaktiv), die aus den Quelldaten hervorgehen. "
            "Schwere: hoch / mittel / gering. Section_number nur setzen, wenn der Bezug klar ist."
        ),
    )


def extract_material(provider, workspace_path, sources: SourceBundle) -> MaterialList:
    src = sources.offer_texts or sources.briefing  # Angebote sind die Hauptquelle für Material
    return _call_llm_json(
        provider,
        workspace_path,
        domain_label="Material + Werkzeug",
        schema_model=MaterialList,
        source_text=src,
        domain_instructions=(
            "Extrahiere Material-Positionen aus den Angeboten (Bezeichnung, Soll-Menge, Einheit, "
            "Bauabschnitt-Zuordnung wenn erkennbar). kind=material oder werkzeug."
        ),
    )


# ───────────────────────────────────────────────────────────────────────────
# Upserts — write extracted data into ORM tables
# ───────────────────────────────────────────────────────────────────────────


_USERNAME_RE = re.compile(r"[^a-z0-9]+")
_ROLE_GLOBAL_MAP = {
    "projektleitung": "projektleitung",
    "bauleitung": "bauleitung",
    "obermonteur": "obermonteur",
    "monteur": "monteur",
    "external": "monteur",
}


def _slugify_name(name: str) -> str:
    base = _USERNAME_RE.sub("_", name.lower()).strip("_")
    return base or "user"


def upsert_project_stamm(db: Session, project: Project, extract: ProjectStamm) -> dict[str, int]:
    if extract.address: project.address = extract.address
    if extract.responsible: project.responsible = extract.responsible
    if extract.construction_manager: project.construction_manager = extract.construction_manager
    if extract.foreman: project.foreman = extract.foreman
    if extract.planned_start: project.planned_start = extract.planned_start
    if extract.planned_end: project.planned_end = extract.planned_end
    if extract.project_type: project.project_type = extract.project_type

    by_number = {s.number: s for s in project.sections}
    sections_written = 0
    schedules_written = 0
    for sx in extract.sections:
        section = by_number.get(sx.number)
        if section is None:
            section = ProjectSection(project_id=project.id, number=sx.number, name=sx.name)
            db.add(section)
            db.flush()
        section.name = sx.name
        if sx.goal is not None: section.goal = sx.goal
        if sx.planned_hours is not None: section.planned_hours = sx.planned_hours
        if sx.responsible is not None: section.responsible = sx.responsible
        if sx.staff is not None: section.staff = sx.staff
        sections_written += 1
        if sx.start_date or sx.end_date:
            sched = db.query(SectionSchedule).filter(SectionSchedule.section_id == section.id).first()
            if sched is None:
                sched = SectionSchedule(section_id=section.id)
                db.add(sched)
            if sx.start_date: sched.start_date = sx.start_date
            if sx.end_date: sched.end_date = sx.end_date
            schedules_written += 1
    db.commit()
    return {"sections": sections_written, "schedules": schedules_written}


def upsert_personnel(db: Session, project: Project, extract: PersonnelExtract) -> dict[str, int]:
    """Personen werden NICHT automatisch als User angelegt — User-Records
    bleiben in der Hand des Admins. Diese Funktion macht zwei Dinge:

    1. Setzt Project.construction_manager / foreman / responsible auf den
       Namen der ersten extrahierten Person mit der passenden Rolle (nur
       wenn das Feld noch leer ist — Admin-Eingaben werden nicht
       überschrieben).
    2. Verknüpft existierende User per ProjectMember, wenn ein User mit
       passendem Username (slug aus display_name) bereits angelegt ist.
    """
    members_written = 0
    matched_users = 0
    unknown_persons: list[str] = []

    # Schritt 1: Project-Felder befüllen, wenn leer.
    first_by_role: dict[str, str] = {}
    for p in extract.persons:
        first_by_role.setdefault(p.role, p.name)
    if not project.responsible and first_by_role.get("projektleitung"):
        project.responsible = first_by_role["projektleitung"]
    if not project.construction_manager and first_by_role.get("bauleitung"):
        project.construction_manager = first_by_role["bauleitung"]
    if not project.foreman and first_by_role.get("obermonteur"):
        project.foreman = first_by_role["obermonteur"]

    # Schritt 2: Existierende User suchen und als ProjectMember verlinken.
    for p in extract.persons:
        username = _slugify_name(p.name)
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            unknown_persons.append(p.name)
            continue
        matched_users += 1
        link = (
            db.query(ProjectMember)
            .filter(ProjectMember.project_id == project.id, ProjectMember.user_id == user.id)
            .first()
        )
        if link is None:
            db.add(ProjectMember(project_id=project.id, user_id=user.id, project_role=p.role))
            members_written += 1
        else:
            link.project_role = p.role

    db.commit()
    return {
        "persons_seen": len(extract.persons),
        "matched_users": matched_users,
        "members_linked": members_written,
        "unknown_persons": unknown_persons,  # type: ignore[dict-item]
    }


def upsert_risks(db: Session, project: Project, extract: RisksExtract) -> dict[str, int]:
    # Avoid duplicates: skip if a row with the same (kind, description, section_number) exists.
    existing = {
        (r.kind, r.section_number, r.description.strip().lower())
        for r in db.query(RiskIssue).filter(RiskIssue.project_id == project.id).all()
    }
    written = 0
    for r in extract.risks:
        key = (r.kind, r.section_number, r.description.strip().lower())
        if key in existing:
            continue
        db.add(RiskIssue(
            project_id=project.id,
            section_number=r.section_number,
            kind=r.kind, description=r.description, severity=r.severity,
            responsible=r.responsible, status="offen", due_date=r.due_date,
        ))
        existing.add(key)
        written += 1
    db.commit()
    return {"risks_new": written}


def upsert_material(db: Session, project: Project, extract: MaterialList) -> dict[str, int]:
    existing = {
        (m.kind, m.section_number, m.name.strip().lower())
        for m in db.query(MaterialItem).filter(MaterialItem.project_id == project.id).all()
    }
    written = 0
    for m in extract.items:
        key = (m.kind, m.section_number, m.name.strip().lower())
        if key in existing:
            continue
        db.add(MaterialItem(
            project_id=project.id,
            section_number=m.section_number,
            kind=m.kind, name=m.name,
            soll_qty=m.soll_qty, unit=m.unit, note=m.note,
            status="vorhanden",
        ))
        existing.add(key)
        written += 1
    db.commit()
    return {"material_new": written}


# ───────────────────────────────────────────────────────────────────────────
# Hydraulics auto-import
# ───────────────────────────────────────────────────────────────────────────


_HEATING_HINT_RE = re.compile(r"(heizung|hydraul|heating|circuit|strang|heizkreis)", re.IGNORECASE)


def auto_import_heating(db: Session, project: Project) -> dict[str, int]:
    """Find uploads that look like heating-design files (Excel/CSV with
    heating-hint name) and run them through the existing importer.
    Returns count of circuits imported."""
    if project.heating_design and project.heating_design.circuits:
        return {"heating_skipped": 1}  # already populated, don't overwrite

    candidates = (
        db.query(ProjectUpload)
        .filter(ProjectUpload.project_id == project.id)
        .all()
    )
    for up in candidates:
        path = Path(up.path)
        if not path.exists():
            continue
        suffix = path.suffix.lower()
        if suffix not in {".xlsx", ".xls", ".csv"}:
            continue
        if not _HEATING_HINT_RE.search(up.filename or path.name):
            continue
        try:
            from app.services.heating_importers import detect_importer

            content = path.read_bytes()
            importer = detect_importer(up.filename or path.name, content[:4096])
            if importer is None:
                continue
            preview = importer.parse(up.filename or path.name, content)
            # Persist the auto-detected preview directly when no heating
            # data exists yet. The interactive mapping UI in heating.py
            # remains the path for ambiguous cases.
            d = preview.design
            design = HeatingDesign(
                project_id=project.id,
                source=preview.source,
                source_file=preview.source_file,
                system_type=d.system_type,
                supply_temp_c=d.supply_temp_c,
                return_temp_c=d.return_temp_c,
                delta_t_k=d.delta_t_k,
                total_volume_flow_lph=d.total_volume_flow_lph,
                pump_model=d.pump_model,
                pump_head_pa=d.pump_head_pa,
                notes=d.notes,
            )
            db.add(design)
            db.flush()
            from app.db.orm_models import HeatingCircuit
            for i, c in enumerate(preview.circuits or []):
                db.add(HeatingCircuit(
                    design_id=design.id, position=i,
                    strand=c.strand, room=c.room, floor=c.floor,
                    radiator_type=c.radiator_type, heat_load_w=c.heat_load_w,
                    volume_flow_lph=c.volume_flow_lph, valve_preset=c.valve_preset,
                ))
            db.commit()
            return {"heating_circuits": len(preview.circuits or [])}
        except Exception as exc:  # noqa: BLE001
            # Don't crash the whole extraction over hydraulics — the user can
            # always go through the dedicated importer UI for mapping.
            return {"heating_error": 1, "heating_error_msg": str(exc)[:200]}  # type: ignore[dict-item]
    return {"heating_skipped": 1}


# ───────────────────────────────────────────────────────────────────────────
# Top-level orchestrator
# ───────────────────────────────────────────────────────────────────────────


def run_full_extraction(
    db: Session, project: Project, provider: LLMProvider, workspace_path: str
) -> dict[str, object]:
    """Run all domain extractors in sequence. Returns a per-domain counter
    dict plus error messages (if any). Does NOT raise on per-domain
    failures — partial extraction is logged and proceeds, so a single bad
    domain doesn't block the whole run.

    ``workspace_path`` MUST be the sanitized generator workspace returned
    by ``prepare_sanitized_generator_workspace`` — never the raw project
    workspace, otherwise the PII filter would be bypassed.
    """
    sources = load_sources(Path(workspace_path))
    report: dict[str, object] = {"sources": {
        "briefing_chars": len(sources.briefing),
        "voicenote_chars": len(sources.voicenotes),
        "offer_chars": len(sources.offer_texts),
        "other_chars": len(sources.other_uploads),
    }}

    def _safe(name: str, fn):
        try:
            report[name] = fn()
        except ExtractionError as exc:
            report[f"{name}_error"] = str(exc)[:400]

    _safe("project_stamm", lambda: upsert_project_stamm(db, project, extract_project_stamm(provider, workspace_path, sources)))
    _safe("personnel",     lambda: upsert_personnel(db, project, extract_personnel(provider, workspace_path, sources)))
    _safe("risks",         lambda: upsert_risks(db, project, extract_risks(provider, workspace_path, sources)))
    _safe("material",      lambda: upsert_material(db, project, extract_material(provider, workspace_path, sources)))
    report["heating"] = auto_import_heating(db, project)
    return report
