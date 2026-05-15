from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserRead"


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=80)
    display_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=6)
    global_role: str = Field(default="monteur", pattern="^(admin|projektleitung|bauleitung|obermonteur|monteur|viewer)$")


class UserRead(BaseModel):
    id: int
    username: str
    display_name: str
    global_role: str
    active: bool
    created_at: datetime


class ProjectMemberCreate(BaseModel):
    user_id: int
    project_role: str = Field(pattern="^(projektleitung|bauleitung|obermonteur|monteur|viewer)$")


class ProjectMemberRead(BaseModel):
    id: int
    user_id: int
    username: str
    display_name: str
    project_role: str
