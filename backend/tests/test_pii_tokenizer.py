"""Tests for ``app.services.pii_tokenizer.PiiTokenizer``.

These tests exercise the regex-only fallback path so they remain
deterministic on developer machines and in CI without requiring
presidio or gliner models.
"""
from __future__ import annotations

import pytest

from app.db.orm_models import AnonymizationRun, AnonymizationToken
from app.services.pii_tokenizer import PiiTokenizer


@pytest.fixture()
def tokenizer() -> PiiTokenizer:
    """A fresh tokenizer per test so cached ML loaders never leak."""
    instance = PiiTokenizer()
    # Mark ML loaders as already attempted with no model available so the
    # tokenizer relies solely on its deterministic regex fallback.
    instance._presidio_loaded = True
    instance._gliner_loaded = True
    return instance


def test_tokenize_person_replaces_full_name(db_session, tokenizer: PiiTokenizer) -> None:
    text = "Der Monteur Max Mustermann hat heute frei."
    run, anonymized = tokenizer.tokenize(db_session, text)

    assert "Max Mustermann" not in anonymized
    assert ":PERSON:" in anonymized
    assert isinstance(run, AnonymizationRun)
    assert run.run_id and len(run.run_id) == 32

    tokens = db_session.query(AnonymizationToken).filter_by(run_id=run.id).all()
    assert any(token.entity_type == "PERSON" for token in tokens)


def test_tokenize_email_and_phone(db_session, tokenizer: PiiTokenizer) -> None:
    text = "Kontakt: max@example.com oder +49 30 1234567 anrufen."
    _run, anonymized = tokenizer.tokenize(db_session, text)

    assert "max@example.com" not in anonymized
    assert "1234567" not in anonymized
    assert ":EMAIL:" in anonymized
    assert ":PHONE:" in anonymized


def test_tokenize_address_pattern(db_session, tokenizer: PiiTokenizer) -> None:
    # The fallback regex looks for "<Token>... <road-keyword> <number>", so we
    # need a separate word before the keyword (e.g. "Berliner Strasse 12").
    text = "Lieferung an Berliner Strasse 12 morgen frueh."
    _run, anonymized = tokenizer.tokenize(db_session, text)

    assert "Berliner Strasse 12" not in anonymized
    assert ":ADDRESS:" in anonymized


def test_tokenize_different_entity_types_get_distinct_placeholders(
    db_session, tokenizer: PiiTokenizer
) -> None:
    """Distinct entity types must each be tokenised with their own placeholder family."""
    text = "Anruf von Max Mustermann unter max@example.com."
    _run, anonymized = tokenizer.tokenize(db_session, text)

    placeholders = [
        segment.strip(".,;")
        for segment in anonymized.split()
        if segment.startswith("[[PII:")
    ]
    assert any("PERSON" in p for p in placeholders)
    assert any("EMAIL" in p for p in placeholders)
    # Placeholders for different types must be distinct strings.
    person_phs = {p for p in placeholders if "PERSON" in p}
    email_phs = {p for p in placeholders if "EMAIL" in p}
    assert person_phs.isdisjoint(email_phs)


def test_tokenize_is_idempotent_for_same_value(db_session, tokenizer: PiiTokenizer) -> None:
    """A value that appears multiple times must map to one placeholder and one DB row."""
    text = "Max Mustermann schreibt an Max Mustermann ueber Max Mustermann."
    run, anonymized = tokenizer.tokenize(db_session, text)

    placeholders = {
        segment.strip(".,;")
        for segment in anonymized.split()
        if segment.startswith("[[PII:")
    }
    person_placeholders = {p for p in placeholders if "PERSON" in p}
    assert len(person_placeholders) == 1, f"expected one placeholder, got {person_placeholders}"

    db_session.refresh(run)
    person_tokens = [token for token in run.tokens if token.entity_type == "PERSON"]
    assert len(person_tokens) == 1, "duplicate values must be stored only once"


def test_reidentify_restores_original_text(db_session, tokenizer: PiiTokenizer) -> None:
    text = "Anruf von Max Mustermann unter max@example.com."
    run, anonymized = tokenizer.tokenize(db_session, text)

    restored, replaced = tokenizer.reidentify(
        db_session, run_id=run.run_id, text=anonymized, mode="internal"
    )
    assert replaced >= 1
    assert "Max Mustermann" in restored
    assert "max@example.com" in restored


def test_reidentify_external_mode_is_noop(db_session, tokenizer: PiiTokenizer) -> None:
    text = "Anruf von Max Mustermann."
    run, anonymized = tokenizer.tokenize(db_session, text)

    restored, replaced = tokenizer.reidentify(
        db_session, run_id=run.run_id, text=anonymized, mode="external"
    )
    assert replaced == 0
    assert restored == anonymized


def test_reidentify_unknown_run_raises(db_session, tokenizer: PiiTokenizer) -> None:
    with pytest.raises(ValueError):
        tokenizer.reidentify(db_session, run_id="does-not-exist", text="x", mode="internal")


def test_run_manifest_records_metadata(db_session, tokenizer: PiiTokenizer) -> None:
    run, _ = tokenizer.tokenize(
        db_session,
        "Mail: max@example.com",
        scope="project:test:input.json",
        mode="internal",
    )
    assert run.scope == "project:test:input.json"
    assert run.mode == "internal"
    assert run.expires_at is not None
