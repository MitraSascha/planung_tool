import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.db.database import get_db
from app.db.orm_models import Project, ProjectMember, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

ADMIN_ROLES = {"admin", "projektleitung"}
SITE_LEAD_ROLES = {"admin", "projektleitung", "bauleitung", "obermonteur"}
PROJECT_READ_ROLES = {"admin", "projektleitung", "bauleitung", "obermonteur", "monteur", "viewer"}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"pbkdf2_sha256${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, salt_b64, digest_b64 = password_hash.split("$", 2)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
    except ValueError:
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return hmac.compare_digest(actual, expected)


def create_access_token(user: User) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_minutes)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.global_role,
        "exp": int(expires_at.timestamp()),
    }
    return _encode_jwt(payload)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        payload = _decode_jwt(token)
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid authentication token") from None

    user = db.query(User).filter(User.id == user_id, User.active.is_(True)).one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


def require_global_role(user: User, allowed_roles: set[str]) -> None:
    if user.global_role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")


def project_role(db: Session, user: User, project: Project) -> str | None:
    if user.global_role in ADMIN_ROLES:
        return user.global_role

    membership = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project.id, ProjectMember.user_id == user.id)
        .one_or_none()
    )
    return membership.project_role if membership else None


def require_project_role(db: Session, user: User, project: Project, allowed_roles: set[str]) -> str:
    role = project_role(db, user, project)
    if role not in allowed_roles:
        raise HTTPException(status_code=403, detail="No access to this project")
    return role


def seed_initial_admin(db: Session) -> None:
    existing = db.query(User).filter(User.username == settings.initial_admin_username).one_or_none()
    if existing is not None:
        return

    db.add(
        User(
            username=settings.initial_admin_username,
            display_name="Administrator",
            password_hash=hash_password(settings.initial_admin_password),
            global_role="admin",
        )
    )
    db.commit()


def _encode_jwt(payload: dict[str, Any]) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64_json(header)
    payload_b64 = _b64_json(payload)
    signature = hmac.new(
        settings.jwt_secret.encode("utf-8"),
        f"{header_b64}.{payload_b64}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return f"{header_b64}.{payload_b64}.{_b64(signature)}"


def _decode_jwt(token: str) -> dict[str, Any]:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".", 2)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authentication token") from None

    expected_signature = hmac.new(
        settings.jwt_secret.encode("utf-8"),
        f"{header_b64}.{payload_b64}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(_b64(expected_signature), signature_b64):
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    payload = json.loads(_b64_decode(payload_b64))
    if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
        raise HTTPException(status_code=401, detail="Authentication token expired")
    return payload


def _b64_json(value: dict[str, Any]) -> str:
    return _b64(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def _b64_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8"))
