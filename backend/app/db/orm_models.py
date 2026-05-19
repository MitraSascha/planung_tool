from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(63), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    project_type: Mapped[str] = mapped_column(String(32), default="standard")
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Auftraggeber/Bauherr (extern, Kunde) — separates Feld!
    # 'responsible' ist der interne Projektverantwortliche (Mitra-Projektleiter).
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    responsible: Mapped[str | None] = mapped_column(String(255), nullable=True)
    construction_manager: Mapped[str | None] = mapped_column(String(255), nullable=True)
    foreman: Mapped[str | None] = mapped_column(String(255), nullable=True)
    planned_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    # HERO ProjectMatch-ID für Tracking-Time-Push. Admin setzt manuell
    # (Suche via globalsearch ist im UI angebunden).
    hero_project_match_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
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
    heating_design: Mapped["HeatingDesign | None"] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        uselist=False,
    )
    offers: Mapped[list["Offer"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Offer.created_at.desc()",
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
    staff_members: Mapped[list["ProjectSectionStaff"]] = relationship(
        back_populates="section",
        cascade="all, delete-orphan",
    )


class ProjectSectionStaff(Base):
    __tablename__ = "project_section_staff"
    __table_args__ = (UniqueConstraint("section_id", "user_id", name="uq_section_staff_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("project_sections.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    section: Mapped["ProjectSection"] = relationship(back_populates="staff_members")
    user: Mapped["User"] = relationship()


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
    progress_current: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=1)
    current_step: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    # HERO-Mapping für Tracking-Time-Push. NULL bis der Partner-Sync gelaufen
    # ist oder der Admin manuell gesetzt hat. Mehrdeutige Namens-Matches
    # bleiben bewusst leer — Admin entscheidet.
    hero_partner_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
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
    report_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="green")
    team: Mapped[str | None] = mapped_column(String(255), nullable=True)
    completed_work: Mapped[str | None] = mapped_column(Text, nullable=True)
    open_work: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Roh-Eingabe der „Arbeitstagerfassung" (Voice oder Text in einem Feld).
    # Wird vom LLM in completed_work + open_work gesplittet (siehe
    # services/arbeitstagerfassung.py). Quelle bleibt persistent, damit
    # Re-Splits beim Edit reproduzierbar sind und der Originaltext (z.B. nicht-
    # deutsche Voice-Aufnahme) für Audit/Korrektur erhalten bleibt.
    raw_work_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Sprach-Code der Roh-Eingabe (Whisper Auto-Detect, ISO 639-1). Nützlich
    # für die Bauleitung um zu sehen ob die Übersetzung getriggert wurde.
    raw_work_log_language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    material_missing: Mapped[str | None] = mapped_column(Text, nullable=True)
    blockers: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Sicherheits-Pre-Check (BG/Versicherung-Compliance). Optional, weil
    # Monteur sie auch auf Papier abhaken kann (Tagescheckliste).
    # NULL = nicht erfasst; True/False = explizit gemeldet.
    safety_psa: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    safety_tools: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    safety_material: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    safety_workarea: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    safety_approval: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ist_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    project: Mapped[Project] = relationship()
    user: Mapped[User] = relationship()
    attendees: Mapped[list["DailyReportAttendee"]] = relationship(
        back_populates="daily_report",
        cascade="all, delete-orphan",
    )


class DailyReportAttendee(Base):
    """Strukturierte Anwesenheits-Liste pro Tagesbericht.

    Wer war an diesem Tag auf der Baustelle? Daraus speist sich der
    automatisch generierte Teamstatus (jeder Anwesende erbt den
    Bericht-Status für diesen Tag).
    """

    __tablename__ = "daily_report_attendees"
    __table_args__ = (
        UniqueConstraint("daily_report_id", "user_id", name="uq_daily_attendee"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    daily_report_id: Mapped[int] = mapped_column(
        ForeignKey("daily_reports.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    daily_report: Mapped[DailyReport] = relationship(back_populates="attendees")
    user: Mapped[User] = relationship()


class WeeklyReport(Base):
    __tablename__ = "weekly_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    week_start: Mapped[date] = mapped_column(Date)
    week_end: Mapped[date] = mapped_column(Date)
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
    # Beschaffungs-Workflow (Stepper): Offen -> Bestellt -> Unterwegs -> Angekommen.
    # Linear, aber rücksetzbar — Audit-Spalten (``*_at`` / ``*_by_user_id``)
    # bleiben beim Zurücksetzen erhalten (Historie statt Auslöschen).
    procurement_status: Mapped[str] = mapped_column(
        String(16), default="offen", server_default="offen", index=True,
    )
    ordered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    ordered_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    shipped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    shipped_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    arrived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    arrived_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    # Auto-Sync-Anker: gesetzt, wenn dieser Issue aus dem Freitext-Feld
    # ``DailyReport.material_missing`` synchronisiert wurde. Updates am
    # Bericht aktualisieren die Zeile statt zu duplizieren.
    source_daily_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("daily_reports.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    project: Mapped[Project] = relationship()
    user: Mapped[User] = relationship(foreign_keys=[user_id])
    ordered_by: Mapped["User | None"] = relationship(
        foreign_keys=[ordered_by_user_id]
    )
    shipped_by: Mapped["User | None"] = relationship(
        foreign_keys=[shipped_by_user_id]
    )
    arrived_by: Mapped["User | None"] = relationship(
        foreign_keys=[arrived_by_user_id]
    )


class Blocker(Base):
    __tablename__ = "blockers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    section_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    status: Mapped[str] = mapped_column(String(32), default="open")
    # Auto-Sync-Anker (analog ``MaterialIssue``): Quelle aus dem
    # Freitext-Feld ``DailyReport.blockers``.
    source_daily_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("daily_reports.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
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


class HeatingDesign(Base):
    __tablename__ = "heating_designs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True
    )

    system_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    supply_temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    delta_t_k: Mapped[float | None] = mapped_column(Float, nullable=True)
    pump_head_pa: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_volume_flow_lph: Mapped[float | None] = mapped_column(Float, nullable=True)
    pump_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[str] = mapped_column(String(64), default="manual")
    source_file: Mapped[str | None] = mapped_column(String(512), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    imported_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    project: Mapped[Project] = relationship(back_populates="heating_design")
    circuits: Mapped[list["HeatingCircuit"]] = relationship(
        back_populates="design",
        cascade="all, delete-orphan",
        order_by="HeatingCircuit.position",
    )
    imported_by: Mapped["User | None"] = relationship()


class HeatingCircuit(Base):
    __tablename__ = "heating_circuits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    design_id: Mapped[int] = mapped_column(
        ForeignKey("heating_designs.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer, default=0)

    strand: Mapped[str | None] = mapped_column(String(128), nullable=True)
    room: Mapped[str | None] = mapped_column(String(255), nullable=True)
    floor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    radiator_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    area_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    heat_load_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_flow_lph: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure_drop_pa: Mapped[float | None] = mapped_column(Float, nullable=True)
    pipe_length_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    valve_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    valve_preset: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kv_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    design: Mapped[HeatingDesign] = relationship(back_populates="circuits")


class ExternalSourceMapping(Base):
    """Persisted column mappings for the generic-table heating importer.

    Once a Bauleiter has mapped the columns of an Architecture-office Excel
    file, the mapping is stored here and proposed on the next upload that
    matches the same source name.
    """

    __tablename__ = "external_source_mappings"
    __table_args__ = (UniqueConstraint("name", name="uq_external_source_mapping_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    importer_source: Mapped[str] = mapped_column(String(64))
    column_map_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_by: Mapped["User | None"] = relationship()


class ProjectPhoto(Base):
    """Photo evidence captured on the building site.

    Stores EXIF metadata (GPS, capture timestamp) and a SHA-256 hash so the
    image can be referenced from generated documents and verified against
    tampering attempts later.
    """

    __tablename__ = "project_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    section_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    daily_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("daily_reports.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    filename: Mapped[str] = mapped_column(String(512))
    path: Mapped[str] = mapped_column(String(1024))
    annotated_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    geo_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    geo_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    project: Mapped[Project] = relationship()
    user: Mapped["User | None"] = relationship()


class VoiceNote(Base):
    """Audio note captured on site, transcribed and fed back into the
    generator as additional context.

    The audio file is stored alongside the project; the transcript is the
    primary payload consumed by the generation pipeline.
    """

    __tablename__ = "voice_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    audio_path: Mapped[str] = mapped_column(String(1024))
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    intent: Mapped[str] = mapped_column(String(32), default="freitext")
    # intent: "daily_report" | "ibn" | "uebergabe" | "freitext"
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transcript_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    transcription_status: Mapped[str] = mapped_column(String(32), default="pending")
    # transcription_status: "pending" | "ok" | "failed"
    transcription_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    transcribed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    project: Mapped[Project] = relationship()
    user: Mapped["User | None"] = relationship()


# ---------------------------------------------------------------------------
# Iteration 4 schema additions
# ---------------------------------------------------------------------------


class PushSubscription(Base):
    """Browser PushManager subscription used by the backend to deliver Web-Push
    notifications via VAPID. One user can subscribe multiple devices."""

    __tablename__ = "push_subscriptions"
    __table_args__ = (
        UniqueConstraint("endpoint", name="uq_push_subscription_endpoint"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    endpoint: Mapped[str] = mapped_column(String(1024))
    p256dh_key: Mapped[str] = mapped_column(String(255))
    auth_key: Mapped[str] = mapped_column(String(255))
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship()


class AuditEvent(Base):
    """Append-only audit log of CRUD operations on sensitive entities.

    Populated via SQLAlchemy event listeners; never updated, only inserted
    and (in retention cleanup) deleted en bloc.
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(32))
    # action: "create" | "update" | "delete" | "anonymize" | "login" | "export"
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    project_slug: Mapped[str | None] = mapped_column(String(63), index=True, nullable=True)
    changes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    user: Mapped["User | None"] = relationship()


class FormResponse(Base):
    """A single user's answer to one field in one generated document.

    The generated HTML carries stable ``data-field-id`` attributes; the
    SPA snippet POSTs each change here so progress and answers persist
    server-side instead of living only in the browser.
    """

    __tablename__ = "form_responses"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "document_path",
            "field_id",
            "filled_by_user_id",
            name="uq_form_response_user_doc_field",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    document_path: Mapped[str] = mapped_column(String(512), index=True)
    field_id: Mapped[str] = mapped_column(String(255))
    # Which value_* column carries the answer. One of: bool, text, number, date.
    value_type: Mapped[str] = mapped_column(String(32))
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_bool: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    value_number: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    filled_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    filled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    filled_by: Mapped["User"] = relationship()


class DocumentTemplate(Base):
    """Jinja2 templates for project documents.

    Replaces the legacy "Codex generates a fresh HTML per run" flow: layouts
    live here, the renderer assembles them with project data from the
    domain tables (ProjectSection, HeatingDesign, Blocker, …).
    """

    __tablename__ = "document_templates"
    __table_args__ = (UniqueConstraint("slug", name="uq_document_template_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), index=True)
    category: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    html_template: Mapped[str] = mapped_column(Text)
    data_schema: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SectionSchedule(Base):
    """Per-section start/end planning. Once a row exists for a section, the
    renderer uses it instead of the stundenanteil-derived schedule — so the
    real termin propagates into Gantt, Wochenplan, Meilensteinplan etc.
    automatically.
    """

    __tablename__ = "section_schedules"
    __table_args__ = (UniqueConstraint("section_id", name="uq_section_schedule_section"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("project_sections.id", ondelete="CASCADE"))
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    section: Mapped["ProjectSection"] = relationship()


class TeamStatusEntry(Base):
    """Daily team status — one row per (project, user, day). Replaces the
    hard-coded 2-row Teamstatus table; new people just add new rows.
    """

    __tablename__ = "team_status"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", "day", name="uq_team_status_per_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    day: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(16), default="green")
    # status: "green" | "yellow" | "red"
    soll_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    ist_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped[Project] = relationship()
    user: Mapped[User] = relationship()


class MaterialItem(Base):
    """Material and tool inventory per project (and optionally per section).
    Replaces the 4-section hard-coded "Material & Werkzeug" list with a
    dynamic, extendable inventory.
    """

    __tablename__ = "material_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    offer_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("offer_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    section_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="material")
    # kind: "material" | "werkzeug"
    name: Mapped[str] = mapped_column(String(255))
    soll_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    ist_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="vorhanden")
    # status: "vorhanden" | "fehlt" | "bestellt" | "geliefert"
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # source markiert die Herkunft des MaterialItem — Basis für Nachkalkulation
    # und Nachträge. „artikelstamm" = ad-hoc vom Großhandel, NICHT im Angebot.
    # „offer" = aus einem Angebot übernommen. „manual" = von Hand angelegt
    # (Werkzeug, Initial-Inventar). „daily_report_freitext" = automatisch aus
    # einem Tagesbericht-Material-Freitext erzeugt.
    source: Mapped[str] = mapped_column(String(32), default="manual", index=True)
    artikelstamm_artikelnummer: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    artikelstamm_preis_eur: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped[Project] = relationship()


class RiskIssue(Base):
    """Risks and defects per project. Replaces the 13 hard-coded rows of the
    Risiken-und-Maengel template with a dynamic, extendable list.
    """

    __tablename__ = "risk_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    section_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="risiko")
    # kind: "risiko" | "mangel"
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16), default="mittel")
    # severity: "hoch" | "mittel" | "gering"
    responsible: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="offen")
    # status: "offen" | "in_arbeit" | "erledigt"
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped[Project] = relationship()


class Offer(Base):
    """A supplier offer (Angebot) attached to a project.

    One project typically receives 2-4 offers from different suppliers
    (own quote, competitor, sub-contractor). Items hold the line-by-line
    positions; the offer header keeps totals and supplier metadata.
    """

    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )

    supplier_name: Mapped[str] = mapped_column(String(255))
    offer_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    offer_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    total_net_eur: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_gross_eur: Mapped[float | None] = mapped_column(Float, nullable=True)
    vat_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # source_type: "xlsx" | "csv" | "ugl" | "pdf" | "manual"
    source_type: Mapped[str] = mapped_column(String(16), default="manual")
    source_file: Mapped[str | None] = mapped_column(String(512), nullable=True)
    attached_file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    imported_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    project: Mapped[Project] = relationship(back_populates="offers")
    items: Mapped[list["OfferItem"]] = relationship(
        back_populates="offer",
        cascade="all, delete-orphan",
        order_by="OfferItem.position_index",
    )
    imported_by: Mapped["User | None"] = relationship()


class OfferItem(Base):
    __tablename__ = "offer_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_id: Mapped[int] = mapped_column(
        ForeignKey("offers.id", ondelete="CASCADE"), index=True
    )
    # Sortier-Index (echte Reihenfolge); ``position_label`` darf "1.001" etc. sein.
    position_index: Mapped[int] = mapped_column(Integer, default=0)
    position_label: Mapped[str | None] = mapped_column(String(32), nullable=True)

    article_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    unit_price_net_eur: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_net_eur: Mapped[float | None] = mapped_column(Float, nullable=True)
    vat_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    offer: Mapped[Offer] = relationship(back_populates="items")


class DataRetentionRule(Base):
    """Configurable retention windows per entity type. Cleanup job deletes
    or anonymises rows older than ``ttl_days``."""

    __tablename__ = "data_retention_rules"
    __table_args__ = (
        UniqueConstraint("entity_type", name="uq_retention_rule_entity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    ttl_days: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(16), default="delete")
    # action: "delete" | "anonymize"
    enabled: Mapped[bool] = mapped_column(default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )



class MaterialCatalogItem(Base):
    """Kuratierter Artikel-Stamm für die Materialerfassung im Tagesbericht.

    Wird aus ``Materialliste.csv`` importiert (siehe
    ``services/material_catalog.py``). Re-Import ist idempotent: existierende
    Artikel werden geupdated, fehlende auf ``active=False`` gesetzt, neue
    angelegt. So bleibt die History erhalten falls eine Materialmeldung auf
    einen mittlerweile abgekündigten Artikel verweist.
    """

    __tablename__ = "material_catalog"
    __table_args__ = (
        UniqueConstraint("artikelnummer", name="uq_material_catalog_artikelnummer"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    artikelnummer: Mapped[str] = mapped_column(String(32), nullable=False)
    beschreibung_1: Mapped[str] = mapped_column(String(255), nullable=False)
    beschreibung_2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    listenpreis_eur: Mapped[float | None] = mapped_column(Float, nullable=True)
    nettowert_eur: Mapped[float | None] = mapped_column(Float, nullable=True)
    einheit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Kategorie aus dem Dateinamen abgeleitet: standard | brandschutz | isolierung.
    # NULL nur bei vor-Migrations-Daten — der Import füllt das immer.
    kategorie: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    # Material-Typ aus den Beschreibungs-Texten abgeleitet:
    # rohr | ventil | formstueck | sonstiges. Auto-Klassifikation beim Import.
    typ: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    sort_key: Mapped[str] = mapped_column(String(512), default="", server_default="")
    active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MaterialUsage(Base):
    """Verbrauchsbuchung: pro Daily-Report wird festgehalten,
    wieviel von welchem Material an einem Tag verbaut wurde.
    `material_items.ist_qty` wird applikationsseitig als Summe der
    Buchungen eines Items aggregiert (siehe services/material_usage.py).
    """

    __tablename__ = "material_usages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    material_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("material_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    daily_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("daily_reports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    section_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qty_used: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    used_at: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    project: Mapped[Project] = relationship()
    material_item: Mapped["MaterialItem | None"] = relationship()


class Milestone(Base):
    """Projekt-Meilenstein. Drei Typen werden automatisch befüllt
    (siehe services/milestones.py), 'custom' ist für manuelle Einträge.
    """

    __tablename__ = "milestones"
    __table_args__ = (
        UniqueConstraint("project_id", "type", "section_id", name="uq_milestone_proj_type_section"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(32), index=True)
    # type: 'section_end' | 'druckpruefung' | 'inbetriebnahme' | 'custom'
    section_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_sections.id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    # status: 'pending' | 'done' | 'overdue'
    auto_generated: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped[Project] = relationship()
    section: Mapped["ProjectSection | None"] = relationship()
