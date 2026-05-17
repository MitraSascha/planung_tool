from datetime import date, datetime

from pydantic import BaseModel, Field


class DailyReportCreate(BaseModel):
    section_number: int | None = None
    report_date: date
    status: str = Field(default="green", pattern="^(green|yellow|red)$")
    team: str | None = None
    completed_work: str | None = None
    open_work: str | None = None
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


class MaterialIssueUpdate(BaseModel):
    status: str = Field(pattern="^(open|in_progress|done)$")


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
