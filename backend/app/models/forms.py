"""Pydantic models for the form-responses API.

The shape mirrors the on-disk HTML: each fillable element carries a
stable ``data-field-id`` and a typed value (bool for checkboxes, text
for free-form cells, number for numeric inputs, date for date pickers).
"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


FormValueType = Literal["bool", "text", "number", "date"]


class FormResponseWrite(BaseModel):
    """Single-field write — used both for initial create and updates."""

    field_id: str = Field(min_length=1, max_length=255)
    value_type: FormValueType
    value_bool: bool | None = None
    value_text: str | None = None
    value_number: float | None = None
    value_date: date | None = None

    @model_validator(mode="after")
    def _exactly_one_value_for_type(self) -> "FormResponseWrite":
        # Only the value_* column matching value_type may be set. Anything
        # else is rejected to keep the row unambiguous — the read path
        # picks the typed column based on value_type and ignoring stray
        # cross-type values would mask client bugs.
        matched = {
            "bool": self.value_bool,
            "text": self.value_text,
            "number": self.value_number,
            "date": self.value_date,
        }
        active = matched[self.value_type]
        # None is a legal "cleared" value for any type (e.g. unchecked
        # checkbox can be sent as value_bool=False, or text cleared to "").
        for other_type, other_value in matched.items():
            if other_type == self.value_type:
                continue
            if other_value is not None:
                raise ValueError(
                    f"value_{other_type} must be null when value_type='{self.value_type}'"
                )
        # active itself may be None / False / "" — that's how a user clears
        # a field, so we don't reject it here.
        _ = active
        return self


class FormResponseRead(FormResponseWrite):
    """Single-field read — adds metadata about who answered and when."""

    project_slug: str
    document_path: str
    filled_by_user_id: int
    filled_by_username: str | None = None
    filled_at: datetime
    updated_at: datetime


class DocumentResponses(BaseModel):
    """Bundle returned for one document: all fields for one user (own
    view) or grouped per user (aggregate view) — the API picks based on
    the endpoint."""

    project_slug: str
    document_path: str
    responses: list[FormResponseRead] = Field(default_factory=list)


class ProjectResponsesAggregate(BaseModel):
    """All responses for the whole project, used by Bauleitung /
    Projektleitung for status overviews."""

    project_slug: str
    documents: list[DocumentResponses] = Field(default_factory=list)
