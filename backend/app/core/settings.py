from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://hez:hez_dev_password@postgres:5432/hez_tool"
    storage_root: Path = Path("/storage")
    reference_schema_path: Path = Path("/reference_schema")
    codex_profile: str = "hez-generator"
    codex_model: str | None = None
    gliner_model_name: str = "urchade/gliner_multi_pii-v1"
    privacy_mapping_ttl_hours: int = 24
    jwt_secret: str = "change-me-in-production"
    jwt_access_token_minutes: int = 480
    initial_admin_username: str = "admin"
    initial_admin_password: str = "admin"
    public_base_domain: str = "hez.tech-artist.de"

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
