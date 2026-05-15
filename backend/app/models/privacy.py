from datetime import datetime

from pydantic import BaseModel, Field


class PrivacyToken(BaseModel):
    placeholder: str
    entity_type: str
    original_text: str | None = None
    source: str
    start: int
    end: int
    confidence: float | None = None


class TokenizeRequest(BaseModel):
    text: str = Field(min_length=1)
    scope: str | None = None
    mode: str = Field(default="internal", pattern="^(internal|external)$")
    include_mapping: bool = False


class TokenizeResponse(BaseModel):
    run_id: str
    mode: str
    anonymized_text: str
    tokens: list[PrivacyToken] = Field(default_factory=list)
    expires_at: datetime | None = None


class ReidentifyRequest(BaseModel):
    run_id: str
    text: str
    mode: str = Field(default="internal", pattern="^(internal|external)$")


class ReidentifyResponse(BaseModel):
    run_id: str
    mode: str
    text: str
    replaced_count: int


class PrivacyHealthResponse(BaseModel):
    presidio_available: bool
    gliner_available: bool
    gliner_model_name: str
    fallback_recognizers: list[str]
