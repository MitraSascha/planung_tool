"""Smoke tests for the placeholder-aware reidentify helper.

The helper underpins role-aware output-file serving: staff roles
(admin/projektleitung/bauleitung/obermonteur) see the original PII,
while monteur/viewer see the on-disk placeholders unchanged. We don't
need the full LLM/Presidio pipeline for these tests — we seed
``anonymization_runs`` + ``anonymization_tokens`` rows directly and
check the lookup-and-replace behaviour.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.db.orm_models import AnonymizationRun, AnonymizationToken
from app.services.pii_tokenizer import PiiTokenizer


@pytest.fixture
def tokenizer() -> PiiTokenizer:
    return PiiTokenizer()


def _seed_run(db_session, placeholder: str, original: str, entity_type: str = "PERSON") -> None:
    run = AnonymizationRun(
        run_id="aaaaaaaa11111111",
        mode="internal",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db_session.add(run)
    db_session.flush()
    db_session.add(
        AnonymizationToken(
            run_id=run.id,
            placeholder=placeholder,
            entity_type=entity_type,
            original_text=original,
            normalized_text=original.casefold(),
            source="seed",
            start=0,
            end=len(original),
            confidence=1.0,
        )
    )
    db_session.commit()


def test_reidentify_text_replaces_known_placeholder(db_session, tokenizer):
    _seed_run(db_session, "[[PII:aaaaaaaa:PERSON:0001]]", "Max Mustermann")
    result, count = tokenizer.reidentify_text(
        db_session,
        "Kunde: [[PII:aaaaaaaa:PERSON:0001]] hat unterschrieben.",
    )
    assert count == 1
    assert result == "Kunde: Max Mustermann hat unterschrieben."


def test_reidentify_text_leaves_unknown_placeholder_untouched(db_session, tokenizer):
    text = "Ein verwaister Platzhalter: [[PII:ffffffff:ADDRESS:0007]]"
    result, count = tokenizer.reidentify_text(db_session, text)
    assert count == 0
    # Unbekannte Platzhalter werden bewusst NICHT geschluckt, sonst geht
    # bei expired/gc'eden Runs Information stillschweigend verloren.
    assert result == text


def test_reidentify_text_no_placeholders_is_passthrough(db_session, tokenizer):
    text = "Ein ganz normaler Doku-Absatz ohne Platzhalter."
    result, count = tokenizer.reidentify_text(db_session, text)
    assert count == 0
    assert result == text


def test_reidentify_text_replaces_multiple_occurrences(db_session, tokenizer):
    _seed_run(db_session, "[[PII:aaaaaaaa:PERSON:0001]]", "Max Mustermann")
    text = (
        "Kunde [[PII:aaaaaaaa:PERSON:0001]] wohnt ... "
        "Wir treffen [[PII:aaaaaaaa:PERSON:0001]] morgen."
    )
    result, count = tokenizer.reidentify_text(db_session, text)
    assert count == 2
    assert "Max Mustermann" in result
    assert "[[PII:" not in result


def _seed_two_persons(db_session) -> None:
    run = AnonymizationRun(
        run_id="bbbbbbbb22222222",
        mode="internal",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db_session.add(run)
    db_session.flush()
    db_session.add_all([
        AnonymizationToken(
            run_id=run.id,
            placeholder="[[PII:bbbbbbbb:PERSON:0001]]",
            entity_type="PERSON",
            original_text="Anna Bauleitung",
            normalized_text="anna bauleitung",
            source="seed",
            start=0,
            end=15,
            confidence=1.0,
        ),
        AnonymizationToken(
            run_id=run.id,
            placeholder="[[PII:bbbbbbbb:PERSON:0002]]",
            entity_type="PERSON",
            original_text="Hans Kunde",
            normalized_text="hans kunde",
            source="seed",
            start=20,
            end=30,
            confidence=1.0,
        ),
    ])
    db_session.commit()


def test_partial_reveal_only_replaces_whitelisted_names(db_session, tokenizer):
    _seed_two_persons(db_session)
    text = (
        "Bauleitung: [[PII:bbbbbbbb:PERSON:0001]], "
        "Kunde: [[PII:bbbbbbbb:PERSON:0002]]"
    )
    result, count = tokenizer.reidentify_text_partial(
        db_session, text, allowed_original_values=["Anna Bauleitung"]
    )
    assert count == 1
    assert "Anna Bauleitung" in result
    # Customer name must stay tokenised
    assert "[[PII:bbbbbbbb:PERSON:0002]]" in result
    assert "Hans Kunde" not in result


def test_partial_reveal_normalises_whitespace_and_case(db_session, tokenizer):
    _seed_two_persons(db_session)
    text = "Bauleitung: [[PII:bbbbbbbb:PERSON:0001]]"
    # Different casing / leading whitespace must still match.
    result, count = tokenizer.reidentify_text_partial(
        db_session, text, allowed_original_values=["  ANNA   BAULEITUNG  "]
    )
    assert count == 1
    assert "Anna Bauleitung" in result


def test_partial_reveal_with_empty_whitelist_is_passthrough(db_session, tokenizer):
    _seed_two_persons(db_session)
    text = "Bauleitung: [[PII:bbbbbbbb:PERSON:0001]]"
    result, count = tokenizer.reidentify_text_partial(
        db_session, text, allowed_original_values=[None, "", "   "]
    )
    assert count == 0
    assert result == text
