"""Tests for the form-responses API.

Covers the round-trip a generated HTML doc actually walks through:
- Monteur PUTs a checkbox + a text answer for his Tagescheckliste.
- The same Monteur GETs the doc back and sees his own answers.
- A different Monteur on the same project sees only his own (empty) view.
- A Bauleitung user reads the project-wide aggregate and sees both users.
- Authorisation: an unrelated user gets 401/403 paths.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.database import Base, get_db
from app.db.orm_models import Project, ProjectMember, User
from app.main import app
from app.services.auth import (
    create_access_token,
    hash_password,
)


@pytest.fixture()
def client(db_engine, monkeypatch):
    """FastAPI TestClient bound to the per-test SQLite engine.

    Two production-only steps are stubbed out for the in-memory test
    setup:
      - ``init_db`` runs Alembic migrations against the live engine;
        Alembic emits ALTER TABLE statements that SQLite cannot handle
        and the schema is already created by ``db_engine`` via
        ``Base.metadata.create_all``, so we no-op the call.
      - The startup-time hooks for whisper/push/audit listeners touch
        services we don't exercise here; leaving them in place is
        harmless but slow on first import — we don't suppress them.
    """
    from sqlalchemy.orm import sessionmaker

    monkeypatch.setattr("app.main.init_db", lambda: None)

    SessionFactory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

    def override_db():
        session = SessionFactory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _mk_user(db_session, username: str, role: str = "monteur") -> User:
    user = User(
        username=username,
        display_name=username.title(),
        password_hash=hash_password("secret"),
        global_role=role,
        active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _mk_project_with_member(db_session, slug: str, user: User, role: str) -> Project:
    project = Project(slug=slug, name=f"Project {slug}", project_type="standard")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    db_session.add(ProjectMember(project_id=project.id, user_id=user.id, project_role=role))
    db_session.commit()
    return project


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def test_put_creates_then_updates_response(client, db_session):
    monteur = _mk_user(db_session, "anna", role="monteur")
    _mk_project_with_member(db_session, "p1", monteur, "monteur")

    url = "/api/projects/p1/form-responses/01_Monteur/MONTEUR_Tagescheckliste.html"
    # First PUT — creates the row.
    resp = client.put(
        url,
        json={
            "field_id": "01_monteur.tagescheckliste.morgens.helm",
            "value_type": "bool",
            "value_bool": True,
        },
        headers=_bearer(monteur),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["value_bool"] is True
    assert body["filled_by_username"] == "anna"

    # Second PUT — overwrites in place (idempotent on user+doc+field).
    resp = client.put(
        url,
        json={
            "field_id": "01_monteur.tagescheckliste.morgens.helm",
            "value_type": "bool",
            "value_bool": False,
        },
        headers=_bearer(monteur),
    )
    assert resp.status_code == 200
    assert resp.json()["value_bool"] is False


def test_get_returns_only_my_own_answers(client, db_session):
    anna = _mk_user(db_session, "anna", role="monteur")
    bert = _mk_user(db_session, "bert", role="monteur")
    project = _mk_project_with_member(db_session, "p1", anna, "monteur")
    db_session.add(ProjectMember(project_id=project.id, user_id=bert.id, project_role="monteur"))
    db_session.commit()

    doc = "01_Monteur/MONTEUR_Tagescheckliste.html"
    client.put(
        f"/api/projects/p1/form-responses/{doc}",
        json={"field_id": "f1", "value_type": "bool", "value_bool": True},
        headers=_bearer(anna),
    )
    client.put(
        f"/api/projects/p1/form-responses/{doc}",
        json={"field_id": "f1", "value_type": "bool", "value_bool": False},
        headers=_bearer(bert),
    )

    # Anna sees True (her own value), not Bert's False.
    resp = client.get(f"/api/projects/p1/form-responses/{doc}", headers=_bearer(anna))
    assert resp.status_code == 200
    rows = resp.json()["responses"]
    assert len(rows) == 1
    assert rows[0]["value_bool"] is True
    assert rows[0]["filled_by_username"] == "anna"


def test_aggregate_returns_all_users(client, db_session):
    anna = _mk_user(db_session, "anna", role="monteur")
    bert = _mk_user(db_session, "bert", role="monteur")
    lead = _mk_user(db_session, "lead", role="bauleitung")
    project = _mk_project_with_member(db_session, "p1", anna, "monteur")
    db_session.add_all([
        ProjectMember(project_id=project.id, user_id=bert.id, project_role="monteur"),
        ProjectMember(project_id=project.id, user_id=lead.id, project_role="bauleitung"),
    ])
    db_session.commit()

    doc = "01_Monteur/MONTEUR_Tagescheckliste.html"
    client.put(
        f"/api/projects/p1/form-responses/{doc}",
        json={"field_id": "f1", "value_type": "bool", "value_bool": True},
        headers=_bearer(anna),
    )
    client.put(
        f"/api/projects/p1/form-responses/{doc}",
        json={"field_id": "f1", "value_type": "bool", "value_bool": False},
        headers=_bearer(bert),
    )

    resp = client.get("/api/projects/p1/form-responses", headers=_bearer(lead))
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    docs = {d["document_path"]: d["responses"] for d in payload["documents"]}
    assert doc in docs
    usernames = sorted(r["filled_by_username"] for r in docs[doc])
    assert usernames == ["anna", "bert"]


def test_aggregate_forbidden_for_monteur(client, db_session):
    monteur = _mk_user(db_session, "anna", role="monteur")
    _mk_project_with_member(db_session, "p1", monteur, "monteur")
    # Monteur must not see other users' answers — only site-lead roles
    # can pull the project-wide aggregate.
    resp = client.get("/api/projects/p1/form-responses", headers=_bearer(monteur))
    assert resp.status_code == 403


def test_put_rejects_cross_type_value(client, db_session):
    monteur = _mk_user(db_session, "anna", role="monteur")
    _mk_project_with_member(db_session, "p1", monteur, "monteur")
    # value_type=bool but text value sent — must fail validation, not
    # silently land in value_text.
    resp = client.put(
        "/api/projects/p1/form-responses/x.html",
        json={
            "field_id": "f1",
            "value_type": "bool",
            "value_bool": True,
            "value_text": "should not be allowed",
        },
        headers=_bearer(monteur),
    )
    assert resp.status_code == 422


def test_delete_removes_my_response(client, db_session):
    monteur = _mk_user(db_session, "anna", role="monteur")
    _mk_project_with_member(db_session, "p1", monteur, "monteur")
    doc = "01_Monteur/x.html"
    client.put(
        f"/api/projects/p1/form-responses/{doc}",
        json={"field_id": "f1", "value_type": "bool", "value_bool": True},
        headers=_bearer(monteur),
    )
    resp = client.delete(
        f"/api/projects/p1/form-responses/{doc}/field/f1",
        headers=_bearer(monteur),
    )
    assert resp.status_code == 204
    rows = client.get(
        f"/api/projects/p1/form-responses/{doc}",
        headers=_bearer(monteur),
    ).json()["responses"]
    assert rows == []
