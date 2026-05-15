from datetime import datetime

from pydantic import BaseModel, Field


class DailyReportCreate(BaseModel):
    section_number: int | None = None
    report_date: str
    status: str = Field(default="green", pattern="^(green|yellow|red)$")
    team: str | None = None
    completed_work: str | None = None
    open_work: str | None = None
    material_missing: str | None = None
    blockers: str | None = None
    notes: str | None = None


class DailyReportRead(DailyReportCreate):
    id: int
    project_slug: str
    user_id: int
    username: str
    display_name: str
    created_at: datetime


class WeeklyReportCreate(BaseModel):
    week_start: str
    week_end: str
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


class BlockerCreate(BaseModel):
    section_number: int | None = None
    description: str = Field(min_length=1)
    severity: str = Field(default="medium", pattern="^(low|medium|high|critical)$")


class ReportSummary(BaseModel):
    project_slug: str
    daily_reports: int
    weekly_reports: int
    material_issues_open: int
    blockers_open: int
    status_green: int
    status_yellow: int
    status_red: int
