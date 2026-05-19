from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://hez:hez_dev_password@postgres:5432/hez_tool"
    storage_root: Path = Path("/storage")
    reference_schema_path: Path = Path("/reference_schema")
    codex_profile: str = "hez-generator"
    codex_model: str | None = None
    llm_provider: str = "both"
    claude_model: str | None = "claude-sonnet-4-6"
    generator_parallelism: int = 3
    generator_subagent_limit: int = 3
    generator_task_timeout_seconds: int = 60 * 30
    gliner_model_name: str = "urchade/gliner_multi_pii-v1"
    privacy_mapping_ttl_hours: int = 24
    jwt_secret: str = "change-me-in-production"
    jwt_access_token_minutes: int = 480
    initial_admin_username: str = "admin"
    initial_admin_password: str = "admin"
    public_base_domain: str = "hez.tech-artist.de"

    # Whisper / Sprachnotiz-Transkription (Phase 13.2)
    # whisper_provider:
    #   "openai"       -> OpenAI Whisper, mit Codex CLI als Fallback (Empfohlen)
    #   "openai_only"  -> Nur OpenAI, kein Fallback
    #   "codex"        -> Nur Codex CLI (Audio-faehiges Modell)
    #   "local"        -> faster-whisper auf der lokalen CPU/GPU
    #   "chain"        -> Custom-Kette aus whisper_chain (z.B. "openai,local,codex")
    #   "off"          -> Transkription deaktiviert
    whisper_provider: str = "openai"
    whisper_chain: str | None = None
    whisper_model: str = "small"
    openai_api_key: str | None = None
    # Codex-Audio-Modell fuer den Fallback. Wenn None, wird codex_model verwendet.
    codex_audio_model: str | None = None
    # Wenn True: SQLAlchemy-Event-Listener fuer VoiceNote werden NICHT registriert.
    # Wird in Tests via Monkeypatch oder DISABLE_WHISPER_HOOK=1 verwendet, damit
    # keine Background-Threads waehrend der Test-Suite mitlaufen.
    disable_whisper_hook: bool = False

    # Web Push (Phase 14.4)
    # VAPID-Keys werden einmalig generiert (siehe scripts/generate_vapid_keys.py)
    # und in die .env eingetragen. Bei leeren Werten ist Push deaktiviert.
    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    vapid_subject: str = "mailto:admin@hez.tech-artist.de"
    disable_push_hook: bool = False

    # Audit-Log (Phase 16)
    # Wenn True: keine SQLAlchemy-Listener fuer audit events registrieren.
    disable_audit_hook: bool = False

    # Data retention defaults — overridden per entity in DataRetentionRule.
    # Days; 0 = keep forever.
    default_retention_days: int = 0

    # Artikelstamm — externe Großhändler-DB (DATANORM, > 2 Mio Artikel).
    # Wird vom MaterialPicker durchsucht, damit Monteure Material aus dem
    # Großhandel anlegen können, das nicht im Projekt-Stamm war (Ad-hoc-Kauf).
    # Leer = Suche deaktiviert (Endpoint liefert 503).
    artikelstamm_db_url: str | None = None

    @property
    def workspaces_path(self) -> Path:
        return self.storage_root / "workspaces"

    @property
    def projects_path(self) -> Path:
        return self.storage_root / "projects"

    @property
    def uploads_path(self) -> Path:
        return self.storage_root / "uploads"


settings = Settings()
