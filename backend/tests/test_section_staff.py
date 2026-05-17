"""Tests for the new ``ProjectSection.staff_members`` many-to-many relation.

We drive the helpers in ``app.api.projects`` directly (without the full
HTTP stack) so that the test focuses on:

- ``_assign_section_staff`` correctly populates ``project_section_staff``,
- replacing the assignment removes the old rows,
- invalid user_ids are silently ignored,
- ``_to_project_read`` exposes the IDs and the brief user info.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.api.projects import _assign_section_staff, _to_project_read
from app.db.orm_models import Project, ProjectSection, ProjectSectionStaff, User
from app.services.auth import hash_password


def _make_user(db: Session, username: str, role: str = "monteur", active: bool = True) -> User:
    user = User(
        username=username,
        display_name=username.title(),
        password_hash=hash_password("pw"),
        global_role=role,
        active=active,
    )
    db.add(user)
    db.flush()
    return user


def _make_project_with_section(db: Session, slug: str) -> tuple[Project, ProjectSection]:
    project = Project(slug=slug, name=f"P {slug}")
    section = ProjectSection(number=1, name="Abschnitt 1")
    project.sections.append(section)
    db.add(project)
    db.flush()
    return project, section


def test_assign_section_staff_creates_rows(db_session: Session) -> None:
    user_a = _make_user(db_session, "alice")
    user_b = _make_user(db_session, "bob")
    _project, section = _make_project_with_section(db_session, "ssa-create")

    _assign_section_staff(db_session, section, [user_a.id, user_b.id])
    db_session.commit()

    rows = db_session.query(ProjectSectionStaff).filter_by(section_id=section.id).all()
    assert {row.user_id for row in rows} == {user_a.id, user_b.id}


def test_assign_section_staff_deduplicates_user_ids(db_session: Session) -> None:
    user_a = _make_user(db_session, "alice2")
    _project, section = _make_project_with_section(db_session, "ssa-dedup")

    _assign_section_staff(db_session, section, [user_a.id, user_a.id, user_a.id])
    db_session.commit()

    rows = db_session.query(ProjectSectionStaff).filter_by(section_id=section.id).all()
    assert len(rows) == 1
    assert rows[0].user_id == user_a.id


def test_assign_section_staff_ignores_invalid_user_ids(db_session: Session) -> None:
    user_a = _make_user(db_session, "alice3")
    _project, section = _make_project_with_section(db_session, "ssa-invalid")

    # 999_999 doesn't exist -> should be silently ignored, valid id still applied.
    _assign_section_staff(db_session, section, [user_a.id, 999_999])
    db_session.commit()

    rows = db_session.query(ProjectSectionStaff).filter_by(section_id=section.id).all()
    assert [row.user_id for row in rows] == [user_a.id]


def test_assign_section_staff_skips_inactive_users(db_session: Session) -> None:
    active_user = _make_user(db_session, "active1")
    inactive_user = _make_user(db_session, "inactive1", active=False)
    _project, section = _make_project_with_section(db_session, "ssa-inactive")

    _assign_section_staff(db_session, section, [active_user.id, inactive_user.id])
    db_session.commit()

    rows = db_session.query(ProjectSectionStaff).filter_by(section_id=section.id).all()
    assert [row.user_id for row in rows] == [active_user.id]


def test_assign_section_staff_replaces_previous_assignment(db_session: Session) -> None:
    user_a = _make_user(db_session, "alice4")
    user_b = _make_user(db_session, "bob4")
    user_c = _make_user(db_session, "carol4")
    _project, section = _make_project_with_section(db_session, "ssa-replace")

    _assign_section_staff(db_session, section, [user_a.id, user_b.id])
    db_session.commit()

    _assign_section_staff(db_session, section, [user_c.id])
    db_session.commit()

    rows = db_session.query(ProjectSectionStaff).filter_by(section_id=section.id).all()
    assert {row.user_id for row in rows} == {user_c.id}


def test_assign_empty_list_clears_assignment(db_session: Session) -> None:
    user_a = _make_user(db_session, "alice5")
    _project, section = _make_project_with_section(db_session, "ssa-clear")

    _assign_section_staff(db_session, section, [user_a.id])
    db_session.commit()
    assert db_session.query(ProjectSectionStaff).filter_by(section_id=section.id).count() == 1

    _assign_section_staff(db_session, section, [])
    db_session.commit()

    assert db_session.query(ProjectSectionStaff).filter_by(section_id=section.id).count() == 0


def test_to_project_read_exposes_staff_user_ids_and_users(db_session: Session, workspace_root) -> None:
    """``_to_project_read`` must surface the relation so the frontend can render names.

    The ``workspace_root`` fixture is required because ``_to_project_read``
    calls into ``_to_upload_read`` / readiness logic that itself doesn't
    touch the filesystem, but ``ProjectRead`` is instantiated with the
    section data we build here.
    """
    user_a = _make_user(db_session, "alice6")
    user_b = _make_user(db_session, "bob6")
    project, section = _make_project_with_section(db_session, "ssa-read")

    _assign_section_staff(db_session, section, [user_a.id, user_b.id])
    db_session.commit()
    db_session.refresh(project)

    read = _to_project_read(project)
    assert len(read.sections) == 1
    section_read = read.sections[0]
    assert set(section_read.staff_user_ids) == {user_a.id, user_b.id}
    usernames = {u.username for u in section_read.staff_users}
    assert usernames == {"alice6", "bob6"}


def test_deleting_section_cascades_to_section_staff(db_session: Session) -> None:
    user_a = _make_user(db_session, "alice7")
    project, section = _make_project_with_section(db_session, "ssa-cascade")

    _assign_section_staff(db_session, section, [user_a.id])
    db_session.commit()
    section_id = section.id
    assert db_session.query(ProjectSectionStaff).filter_by(section_id=section_id).count() == 1

    # Mimic the update_project flow: clearing sections triggers cascade delete.
    project.sections.clear()
    db_session.commit()

    assert db_session.query(ProjectSectionStaff).filter_by(section_id=section_id).count() == 0
