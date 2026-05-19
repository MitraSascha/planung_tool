from datetime import date, datetime, time

from pydantic import BaseModel, Field


class DailyReportCreate(BaseModel):
    section_number: int | None = None
    report_date: date
    # Schichtbeginn (Berlin-Lokalzeit). Optional — wenn None, greift der
    # Setting-Default beim HERO-Push.
    start_time: time | None = None
    status: str = Field(default="green", pattern="^(green|yellow|red)$")
    team: str | None = None  # Freitext-Fallback
    attendee_user_ids: list[int] = Field(default_factory=list)
    completed_work: str | None = None
    open_work: str | None = None
    # Arbeitstagerfassung: ein Roh-Feld. Wenn gesetzt, splittet ein LLM in
    # completed_work + open_work (siehe services/arbeitstagerfassung.py).
    # Frontend kann beide Pfade gleichzeitig liefern — Backend bevorzugt den
    # Roh-Text für den Split, aber überschreibt nicht, wenn der Split leer
    # bliebe.
    raw_work_log: str | None = None
    # ISO 639-1 der Voice-Quelle (kommt aus /api/voice/transcribe). Optional —
    # gibt dem LLM einen Hinweis bei mehrsprachigen Eingaben.
    raw_work_log_language: str | None = None
    material_missing: str | None = None
    blockers: str | None = None
    notes: str | None = None
    ist_hours: float | None = None
    # Sicherheits-Pre-Check (alle optional — NULL = nicht erfasst)
    safety_psa: bool | None = None
    safety_tools: bool | None = None
    safety_material: bool | None = None
    safety_workarea: bool | None = None
    safety_approval: bool | None = None


class DailyReportRead(DailyReportCreate):
    id: int
    project_slug: str
    user_id: int
    username: str
    display_name: str
    created_at: datetime
    editable: bool = False  # vom Endpoint gesetzt — gilt für den aktuellen User


class DailyReportUpdate(BaseModel):
    """Patch-Payload: alle Felder optional, ``report_date`` und ``user_id``
    sind absichtlich nicht enthalten — die Identität des Berichts bleibt
    fest, nur der Inhalt kann nachgetragen werden."""
    section_number: int | None = None
    start_time: time | None = None
    status: str | None = Field(default=None, pattern="^(green|yellow|red)$")
    team: str | None = None
    attendee_user_ids: list[int] | None = None
    completed_work: str | None = None
    open_work: str | None = None
    raw_work_log: str | None = None
    raw_work_log_language: str | None = None
    material_missing: str | None = None
    blockers: str | None = None
    notes: str | None = None
    ist_hours: float | None = None
    safety_psa: bool | None = None
    safety_tools: bool | None = None
    safety_material: bool | None = None
    safety_workarea: bool | None = None
    safety_approval: bool | None = None


class WeeklyReportCreate(BaseModel):
    week_start: date
    week_end: date
    status: str = Field(default="green", pattern="^(green|yellow|red)$")
    summary: str | None = None
    next_week_plan: str | None = None
    manpower_notes: str | None = None
    material_notes: str | None = None
    risks: str | None = None


class WeeklyReportRead(WeeklyReportCreate):
    id: int
    project_slug: str
    user_id: int
    username: str
    display_name: str
    created_at: datetime


class MaterialIssueCreate(BaseModel):
    section_number: int | None = None
    description: str = Field(min_length=1)
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")


class MaterialIssueRead(MaterialIssueCreate):
    id: int
    project_slug: str
    user_id: int
    username: str
    display_name: str
    status: str
    created_at: datetime
    # Beschaffungs-Workflow (Stepper) — siehe ORM-Model.
    procurement_status: str = "offen"
    ordered_at: datetime | None = None
    ordered_by_username: str | None = None
    shipped_at: datetime | None = None
    shipped_by_username: str | None = None
    arrived_at: datetime | None = None
    arrived_by_username: str | None = None


class MaterialIssueUpdate(BaseModel):
    status: str = Field(pattern="^(open|in_progress|done)$")


class MaterialIssueProcurementUpdate(BaseModel):
    """Stepper-PATCH: setzt nur den Beschaffungs-Status (z.B. ``bestellt``).
    Backend setzt automatisch den passenden Timestamp + auslösenden User
    auf der jeweiligen Stufe."""
    procurement_status: str = Field(
        pattern="^(offen|bestellt|unterwegs|angekommen)$",
    )


class BlockerCreate(BaseModel):
    section_number: int | None = None
    description: str = Field(min_length=1)
    severity: str = Field(default="medium", pattern="^(low|medium|high|critical)$")


class BlockerRead(BlockerCreate):
    id: int
    project_slug: str
    user_id: int
    username: str
    display_name: str
    status: str
    created_at: datetime


class BlockerUpdate(BaseModel):
    status: str = Field(pattern="^(open|in_progress|done)$")


class ReportSummary(BaseModel):
    project_slug: str
    daily_reports: int
    weekly_reports: int
    material_issues_open: int
    blockers_open: int
    status_green: int
    status_yellow: int
    status_red: int
