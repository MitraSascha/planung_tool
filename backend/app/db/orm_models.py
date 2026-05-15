from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(63), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    project_type: Mapped[str] = mapped_column(String(32), default="standard")
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    responsible: Mapped[str | None] = mapped_column(String(255), nullable=True)
    construction_manager: Mapped[str | None] = mapped_column(String(255), nullable=True)
    foreman: Mapped[str | None] = mapped_column(String(255), nullable=True)
    planned_start: Mapped[str | None] = mapped_column(String(32), nullable=True)
    planned_end: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    sections: Mapped[list["ProjectSection"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectSection.number",
    )
    generation_runs: Mapped[list["GenerationRun"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    uploads: Mapped[list["ProjectUpload"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectUpload.created_at.desc()",
    )
    members: Mapped[list["ProjectMember"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )


class ProjectSection(Base):
    __tablename__ = "project_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    planned_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    responsible: Mapped[str | None] = mapped_column(String(255), nullable=True)
    staff: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped[Project] = relationship(back_populates="sections")


class ProjectUpload(Base):
    __tablename__ = "project_uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(512))
    path: Mapped[str] = mapped_column(String(1024))
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="uploads")


class GenerationRun(Base):
    __tablename__ = "generation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(32), default="created")
    codex_profile: Mapped[str] = mapped_column(String(255))
    prompt: Mapped[str] = mapped_column(Text)
    returncode: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stdout: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="generation_runs")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    global_role: Mapped[str] = mapped_column(String(32), default="monteur")
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    memberships: Mapped[list["ProjectMember"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_member_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    project_role: Mapped[str] = mapped_column(String(32), default="monteur")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    section_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    report_date: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="green")
    team: Mapped[str | None] = mapped_column(String(255), nullable=True)
    completed_work: Mapped[str | None] = mapped_column(Text, nullable=True)
    open_work: Mapped[str | None] = mapped_column(Text, nullable=True)
    material_missing: Mapped[str | None] = mapped_column(Text, nullable=True)
    blockers: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    project: Mapped[Project] = relationship()
    user: Mapped[User] = relationship()


class WeeklyReport(Base):
    __tablename__ = "weekly_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    week_start: Mapped[str] = mapped_column(String(32))
    week_end: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="green")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_week_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    manpower_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    material_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    risks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship()
    user: Mapped[User] = relationship()


class MaterialIssue(Base):
    __tablename__ = "material_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    section_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    status: Mapped[str] = mapped_column(String(32), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship()
    user: Mapped[User] = relationship()


class Blocker(Base):
    __tablename__ = "blockers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    section_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    status: Mapped[str] = mapped_column(String(32), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship()
    user: Mapped[User] = relationship()


class AnonymizationRun(Base):
    __tablename__ = "anonymization_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    scope: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mode: Mapped[str] = mapped_column(String(32), default="internal")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tokens: Mapped[list["AnonymizationToken"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AnonymizationToken.placeholder",
    )


class AnonymizationToken(Base):
    __tablename__ = "anonymization_tokens"
    __table_args__ = (UniqueConstraint("run_id", "placeholder", name="uq_anonymization_run_placeholder"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("anonymization_runs.id", ondelete="CASCADE"))
    placeholder: Mapped[str] = mapped_column(String(128), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    original_text: Mapped[str] = mapped_column(Text)
    normalized_text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(64))
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[AnonymizationRun] = relationship(back_populates="tokens")
