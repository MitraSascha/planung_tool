from datetime import date, datetime

from pydantic import BaseModel, Field


class StatusBreakdownRead(BaseModel):
    green: int = 0
    yellow: int = 0
    red: int = 0
    total: int = 0


class TimeSeriesPointRead(BaseModel):
    date: date
    value: float
    label: str | None = None


class TopItemRead(BaseModel):
    label: str
    count: int
    severity: str | None = None


class HoursPerUserRead(BaseModel):
    user_id: int
    display_name: str
    soll_hours: float
    ist_hours: float
    days: int


class ProjectAnalyticsRead(BaseModel):
    project_slug: str
    project_name: str
    period_start: date
    period_end: date
    daily_status: StatusBreakdownRead
    weekly_status: StatusBreakdownRead
    blockers_open: int = 0
    blockers_total: int = 0
    blockers_by_severity: dict[str, int] = Field(default_factory=dict)
    material_open: int = 0
    material_total: int = 0
    risks_open: int = 0
    risks_total: int = 0
    materials_by_status: dict[str, int] = Field(default_factory=dict)
    hours_total_soll: float = 0.0
    hours_total_ist: float = 0.0
    hours_by_user: list[HoursPerUserRead] = Field(default_factory=list)
    daily_status_series: list[TimeSeriesPointRead] = Field(default_factory=list)
    blockers_opened_per_day: list[TimeSeriesPointRead] = Field(default_factory=list)
    offer_total_net: float | None = None
    offer_count: int = 0
    top_blockers: list[TopItemRead] = Field(default_factory=list)
    top_material_issues: list[TopItemRead] = Field(default_factory=list)


class AtRiskProjectRead(BaseModel):
    slug: str
    name: str
    recent_red_reports: int
    critical_blockers: int


class PortfolioAnalyticsRead(BaseModel):
    generated_at: datetime
    project_count: int
    active_project_count: int
    projects_at_risk: list[AtRiskProjectRead] = Field(default_factory=list)
    total_hours_ist_last_7d: float = 0.0
    total_hours_soll_last_7d: float = 0.0
    open_blockers_total: int = 0
    open_material_total: int = 0
    open_risks_total: int = 0
    total_offer_value_net: float = 0.0
