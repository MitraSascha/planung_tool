"""Tests for ``app.services.weekly_report_drafter.draft_weekly_report``.

The drafter is async because the underlying provider exposes ``run_async``,
so we drive it via ``asyncio.run`` in each test. We never spawn the real
Codex/Claude CLI: a stub ``LLMProvider`` is injected.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.db.orm_models import DailyReport, Project, User
from app.services.auth import hash_password
from app.services.generator_runner import LLMProvider
from app.services.weekly_report_drafter import (
    WeeklyReportDraft,
    _NO_DAILY_HINT,
    draft_weekly_report,
)


class StubProvider(LLMProvider):
    name = "stub"

    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = "") -> None:
        self._stdout = stdout
        self._returncode = returncode
        self._stderr = stderr
        self.calls: list[tuple[str, str]] = []

    def run(self, workspace_path: str, prompt: str) -> subprocess.CompletedProcess[str]:
        self.calls.append((workspace_path, prompt))
        return subprocess.CompletedProcess(
            args=[],
            returncode=self._returncode,
            stdout=self._stdout,
            stderr=self._stderr,
        )


def _make_user(db: Session, username: str = "alice") -> User:
    user = User(
        username=username,
        display_name=username.title(),
        password_hash=hash_password("pw"),
        global_role="bauleitung",
    )
    db.add(user)
    db.flush()
    return user


def _make_project(db: Session, slug: str = "p1") -> Project:
    project = Project(slug=slug, name=f"Projekt {slug}")
    db.add(project)
    db.flush()
    return project


def _add_daily(
    db: Session,
    project: Project,
    user: User,
    *,
    day: date,
    status: str = "green",
    completed_work: str | None = None,
    blockers: str | None = None,
) -> DailyReport:
    report = DailyReport(
        project_id=project.id,
        user_id=user.id,
        report_date=day,
        status=status,
        completed_work=completed_work,
        blockers=blockers,
    )
    db.add(report)
    db.flush()
    return report


def test_draft_returns_hint_when_no_daily_reports(db_session: Session) -> None:
    user = _make_user(db_session)
    project = _make_project(db_session)
    db_session.commit()

    stub = StubProvider(stdout="should not be called")

    draft: WeeklyReportDraft = asyncio.run(
        draft_weekly_report(
            db_session,
            project,
            date(2026, 5, 11),
            date(2026, 5, 17),
            provider=stub,
        )
    )

    assert draft.summary == _NO_DAILY_HINT
    assert draft.next_week_plan == ""
    assert draft.status == "green"
    # Provider must not be invoked when there is nothing to summarise.
    assert stub.calls == []
    # ``user`` reference kept so the test setup is reused.
    assert user.id is not None


def test_draft_parses_json_response(db_session: Session) -> None:
    user = _make_user(db_session)
    project = _make_project(db_session)
    _add_daily(db_session, project, user, day=date(2026, 5, 12), status="green",
               completed_work="Heizkörper Erdgeschoss montiert")
    _add_daily(db_session, project, user, day=date(2026, 5, 13), status="yellow",
               completed_work="Hydraulik geprüft", blockers="Wartet auf Pumpe")
    db_session.commit()

    stub = StubProvider(
        stdout=(
            '{"summary": "Gute Woche", '
            '"next_week_plan": "Inbetriebnahme", '
            '"manpower_notes": "Team komplett", '
            '"material_notes": "Pumpe fehlt", '
            '"risks": "Liefertermin Pumpe"}'
        )
    )

    draft = asyncio.run(
        draft_weekly_report(
            db_session,
            project,
            date(2026, 5, 11),
            date(2026, 5, 17),
            provider=stub,
        )
    )

    assert draft.summary == "Gute Woche"
    assert draft.next_week_plan == "Inbetriebnahme"
    assert draft.manpower_notes == "Team komplett"
    assert draft.material_notes == "Pumpe fehlt"
    assert draft.risks == "Liefertermin Pumpe"
    # Status derived from daily reports: 1x green + 1x yellow -> yellow.
    assert draft.status == "yellow"
    assert len(stub.calls) == 1


def test_draft_status_red_when_any_daily_red(db_session: Session) -> None:
    user = _make_user(db_session)
    project = _make_project(db_session)
    _add_daily(db_session, project, user, day=date(2026, 5, 12), status="green")
    _add_daily(db_session, project, user, day=date(2026, 5, 13), status="red")
    _add_daily(db_session, project, user, day=date(2026, 5, 14), status="yellow")
    db_session.commit()

    stub = StubProvider(
        stdout='{"summary":"s","next_week_plan":"","manpower_notes":"","material_notes":"","risks":""}'
    )

    draft = asyncio.run(
        draft_weekly_report(
            db_session,
            project,
            date(2026, 5, 11),
            date(2026, 5, 17),
            provider=stub,
        )
    )
    assert draft.status == "red"


def test_draft_falls_back_when_response_not_json(
    db_session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    user = _make_user(db_session)
    project = _make_project(db_session)
    _add_daily(db_session, project, user, day=date(2026, 5, 12), status="green")
    db_session.commit()

    raw = "Sorry, ich kann gerade kein JSON erzeugen. Trotzdem ein paar Notizen."
    stub = StubProvider(stdout=raw)

    with caplog.at_level(logging.WARNING, logger="app.services.weekly_report_drafter"):
        draft = asyncio.run(
            draft_weekly_report(
                db_session,
                project,
                date(2026, 5, 11),
                date(2026, 5, 17),
                provider=stub,
            )
        )

    assert draft.summary == raw
    assert draft.next_week_plan == ""
    assert draft.manpower_notes == ""
    assert draft.material_notes == ""
    assert draft.risks == ""
    assert draft.status == "green"
    assert any("not valid JSON" in record.getMessage() for record in caplog.records)


def test_draft_handles_json_wrapped_in_code_fence(db_session: Session) -> None:
    user = _make_user(db_session)
    project = _make_project(db_session)
    _add_daily(db_session, project, user, day=date(2026, 5, 12), status="green")
    db_session.commit()

    stub = StubProvider(
        stdout=(
            "```json\n"
            '{"summary":"ok","next_week_plan":"weiter","manpower_notes":"",'
            '"material_notes":"","risks":""}\n'
            "```"
        )
    )
    draft = asyncio.run(
        draft_weekly_report(
            db_session, project, date(2026, 5, 11), date(2026, 5, 17), provider=stub
        )
    )
    assert draft.summary == "ok"
    assert draft.next_week_plan == "weiter"
