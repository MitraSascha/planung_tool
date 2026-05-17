"""Pydantic models for the smart anomaly API and weekly-report drafts."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class WeeklyReportDraftRequest(BaseModel):
    week_start: date
    week_end: date


class WeeklyReportDraftRead(BaseModel):
    summary: str = ""
    next_week_plan: str = ""
    manpower_notes: str = ""
    material_notes: str = ""
    risks: str = ""
    status: str = Field(default="green", pattern="^(green|yellow|red)$")


class AnomalyRead(BaseModel):
    project_slug: str
    kind: str
    severity: str
    title: str
    detail: str
    related_ids: list[int] = Field(default_factory=list)
    detected_at: datetime
