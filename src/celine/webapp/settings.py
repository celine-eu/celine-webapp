"""Application settings using pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

from celine.sdk.settings.models import OidcSettings


class Settings(BaseSettings):
    """Application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    oidc: OidcSettings = OidcSettings()

    # Server
    host: str = "0.0.0.0"
    port: int = 8014

    # Database - using asyncpg driver for async support
    database_url: str = (
        "postgresql+asyncpg://postgres:securepassword123@172.17.0.1:15432/celine_webapp"
    )
    database_echo: bool = False

    # Security
    policy_version: str = "2024-01-01"
    jwt_header_name: str = "x-auth-request-access-token"

    # CORS
    cors_origins: list[str] = ["http://localhost:5173"]

    # Optional overrides
    smart_meter_api_url: Optional[str] = None
    digital_twin_api_url: Optional[str] = "http://api.celine.localhost/dt"
    nudging_api_url: Optional[str] = "http://api.celine.localhost/nudging"


# Global settings instance
settings = Settings()
