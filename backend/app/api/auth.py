from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.orm_models import User
from app.models.auth import LoginRequest, TokenResponse, UserCreate, UserRead
from app.services.auth import (
    ADMIN_ROLES,
    create_access_token,
    get_current_user,
    hash_password,
    require_global_role,
    verify_password,
)

router = APIRouter()


def _to_user_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        global_role=user.global_role,
        active=user.active,
        created_at=user.created_at,
    )


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.username == request.username, User.active.is_(True)).one_or_none()
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    return TokenResponse(access_token=create_access_token(user), user=_to_user_read(user))


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> UserRead:
    return _to_user_read(current_user)


@router.get("/users", response_model=list[UserRead])
def list_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[UserRead]:
    require_global_role(current_user, ADMIN_ROLES)
    users = db.query(User).order_by(User.display_name.asc()).all()
    return [_to_user_read(user) for user in users]


@router.post("/users", response_model=UserRead)
def create_user(
    request: UserCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserRead:
    require_global_role(current_user, ADMIN_ROLES)
    user = User(
        username=request.username,
        display_name=request.display_name,
        password_hash=hash_password(request.password),
        global_role=request.global_role,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username already exists") from exc
    db.refresh(user)
    return _to_user_read(user)
