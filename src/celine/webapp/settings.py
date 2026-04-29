"""Application settings using pydantic-settings."""

import socket
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

from celine.sdk.settings.models import OidcSettings


def _is_running_in_container() -> bool:
    return Path("/.dockerenv").exists()


def resolve_local_dev_url(raw_url: str) -> str:
    """Keep host-gateway URLs in containers, fallback to loopback on the host."""

    url = make_url(raw_url)
    if url.host != "host.docker.internal":
        return raw_url

    if _is_running_in_container():
        return raw_url

    try:
        socket.getaddrinfo(url.host, url.port or 0)
        return raw_url
    except socket.gaierror:
        fallback_url = URL.create(
            drivername=url.drivername,
            username=url.username,
            password=url.password,
            host="127.0.0.1",
            port=url.port,
            database=url.database,
            query=url.query,
        )
        return fallback_url.render_as_string(hide_password=False)


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
        "postgresql+asyncpg://postgres:securepassword123@host.docker.internal:15432/celine_webapp"
    )
    database_echo: bool = False

    # Security
    policy_version: str = "2024-01-01"
    jwt_header_name: str = "x-auth-request-access-token"

    # CORS
    cors_origins: list[str] = ["http://localhost:5173"]

    # Optional overrides
    smart_meter_api_url: Optional[str] = None
    digital_twin_api_url: Optional[str] = "http://host.docker.internal:8002"
    nudging_api_url: Optional[str] = "http://host.docker.internal:8016"
    rec_registry_url: Optional[str] = "http://host.docker.internal:8004"
    flexibility_api_url: Optional[str] = "http://host.docker.internal:8017"
    nudging_ingest_scope: str = "nudging.ingest"

    @property
    def resolved_database_url(self) -> str:
        return resolve_local_dev_url(self.database_url)


# Global settings instance
settings = Settings()
