"""Aufbewahrungsfristen (Data Retention) und manueller Cleanup-Job.

Liest die ``DataRetentionRule``-Tabelle und loescht/anonymisiert pro
Entitaet alle Datensaetze, deren ``created_at`` aelter als ``ttl_days``
ist. Wird vom Admin manuell ueber die DSGVO-API getriggert (kein Cron).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.orm_models import (
    AuditEvent,
    Blocker,
    DailyReport,
    DataRetentionRule,
    GenerationRun,
    MaterialIssue,
    VoiceNote,
    WeeklyReport,
)
from app.services import audit_log
from app.services.pii_tokenizer import pii_tokenizer

logger = logging.getLogger(__name__)


ENTITY_REGISTRY: dict[str, type] = {
    "DailyReport": DailyReport,
    "WeeklyReport": WeeklyReport,
    "Blocker": Blocker,
    "MaterialIssue": MaterialIssue,
    "GenerationRun": GenerationRun,
    "AuditEvent": AuditEvent,
    "VoiceNote": VoiceNote,
}

# Welche Textfelder pro Entitaet bei action="anonymize" tokenisiert werden
ANONYMIZE_FIELDS: dict[str, tuple[str, ...]] = {
    "DailyReport": ("team", "completed_work", "open_work", "material_missing", "blockers", "notes"),
    "WeeklyReport": ("summary", "next_week_plan", "manpower_notes", "material_notes", "risks"),
    "Blocker": ("description",),
    "MaterialIssue": ("description",),
    "VoiceNote": ("transcript",),
    "AuditEvent": (),  # Audit-Events koennen nicht sinnvoll anonymisiert werden — nur loeschen
    "GenerationRun": ("prompt", "stdout", "stderr"),
}


def list_retention_rules(db: Session) -> list[DataRetentionRule]:
    return db.query(DataRetentionRule).order_by(DataRetentionRule.entity_type.asc()).all()


def upsert_retention_rule(db: Session, rule_data: dict[str, Any]) -> DataRetentionRule:
    """Inserts or updates a retention rule. ``entity_type`` is the unique key."""
    entity_type = rule_data["entity_type"]
    if entity_type not in ENTITY_REGISTRY:
        raise ValueError(f"Unsupported entity_type: {entity_type}")

    action = rule_data.get("action", "delete")
    if action not in {"delete", "anonymize"}:
        raise ValueError(f"Unsupported action: {action}")

    existing = (
        db.query(DataRetentionRule)
        .filter(DataRetentionRule.entity_type == entity_type)
        .one_or_none()
    )

    if existing is None:
        existing = DataRetentionRule(
            entity_type=entity_type,
            ttl_days=int(rule_data["ttl_days"]),
            action=action,
            enabled=bool(rule_data.get("enabled", True)),
            description=rule_data.get("description"),
        )
        db.add(existing)
    else:
        existing.ttl_days = int(rule_data["ttl_days"])
        existing.action = action
        existing.enabled = bool(rule_data.get("enabled", True))
        existing.description = rule_data.get("description")

    db.commit()
    db.refresh(existing)
    return existing


def delete_retention_rule(db: Session, entity_type: str) -> bool:
    existing = (
        db.query(DataRetentionRule)
        .filter(DataRetentionRule.entity_type == entity_type)
        .one_or_none()
    )
    if existing is None:
        return False
    db.delete(existing)
    db.commit()
    return True


def _cutoff(ttl_days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=ttl_days)


def _anonymize_row(db: Session, entity_type: str, row: Any) -> bool:
    """Anonymisiert die in ``ANONYMIZE_FIELDS`` definierten Felder. Liefert
    ``True``, wenn mindestens ein Feld veraendert wurde.
    """
    fields = ANONYMIZE_FIELDS.get(entity_type, ())
    if not fields:
        return False
    changed = False
    for field in fields:
        current = getattr(row, field, None)
        if current:
            try:
                _, tokenized = pii_tokenizer.tokenize(
                    db=db, text=current, scope=f"retention:{entity_type}:{row.id}:{field}", mode="internal"
                )
                if tokenized != current:
                    setattr(row, field, tokenized)
                    changed = True
            except Exception:  # noqa: BLE001
                setattr(row, field, "[anonymisiert]")
                changed = True
    return changed


def run_retention_cleanup(db: Session, *, dry_run: bool = False) -> dict[str, Any]:
    """Iteriert alle aktiven Regeln und loescht/anonymisiert Rows aelter
    als ``ttl_days``. Gibt Statistiken pro Entitaet zurueck.

    ``dry_run=True`` zaehlt nur die betroffenen Rows, fuehrt aber keine
    Mutationen aus.
    """
    rules = (
        db.query(DataRetentionRule).filter(DataRetentionRule.enabled.is_(True)).all()
    )

    stats: dict[str, dict[str, Any]] = {}

    for rule in rules:
        entity_cls = ENTITY_REGISTRY.get(rule.entity_type)
        if entity_cls is None:
            stats[rule.entity_type] = {
                "action": rule.action,
                "skipped": True,
                "reason": "unknown_entity_type",
                "affected": 0,
            }
            continue
        if rule.ttl_days <= 0:
            stats[rule.entity_type] = {
                "action": rule.action,
                "skipped": True,
                "reason": "ttl_zero",
                "affected": 0,
            }
            continue

        cutoff = _cutoff(rule.ttl_days)
        query = db.query(entity_cls).filter(entity_cls.created_at < cutoff)
        affected_rows = query.all()
        affected = len(affected_rows)

        entry: dict[str, Any] = {
            "action": rule.action,
            "ttl_days": rule.ttl_days,
            "cutoff": cutoff.isoformat(),
            "affected": affected,
            "executed": 0,
        }

        if not dry_run and affected:
            if rule.action == "delete":
                for row in affected_rows:
                    db.delete(row)
                entry["executed"] = affected
            elif rule.action == "anonymize":
                executed = 0
                for row in affected_rows:
                    if _anonymize_row(db, rule.entity_type, row):
                        executed += 1
                entry["executed"] = executed
            db.commit()

            # Audit-Eintrag schreiben (Cleanup-Aktion)
            audit_log.log(
                db,
                action=rule.action,
                entity_type=rule.entity_type,
                entity_id=None,
                project_slug=None,
                changes={"cleanup": True, "ttl_days": rule.ttl_days, "affected": affected},
            )
            db.commit()

        stats[rule.entity_type] = entry

    return {"dry_run": dry_run, "rules": stats}
