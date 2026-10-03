"""Deployment posture: only `CELINE_ENV=dev` accepts the development defaults.

`celine.sdk.posture` treats unset, empty, `staging`, `prod` or a typo as hardened.
The suite runs in dev (conftest), so every test here names its environment.
"""

from __future__ import annotations

import pytest
from celine.sdk.posture import InsecureConfiguration
from celine.sdk.settings.models import OidcSettings

from celine.webapp import main as main_module
from celine.webapp.settings import Settings, posture_guard, settings

HARDENED = ["", "staging"]

DEV_DATABASE_URL = (
    "postgresql+asyncpg://postgres:securepassword123@host.docker.internal:15432/celine_webapp"
)


@pytest.fixture
def no_oidc_env(monkeypatch):
    for name in ("BASE_URL", "JWKS_URI", "AUDIENCE", "CLIENT_ID", "CLIENT_SECRET"):
        monkeypatch.delenv(f"CELINE_OIDC_{name}", raising=False)


def _shipped_defaults(env: str) -> Settings:
    """What a checkout runs with when nothing is configured."""
    return Settings(
        _env_file=None,
        celine_env=env,
        environment="",
        database_url=DEV_DATABASE_URL,
        oidc=OidcSettings(),
    )


def _deployed(env: str) -> Settings:
    return Settings(
        _env_file=None,
        celine_env=env,
        environment="",
        database_url="postgresql+asyncpg://webapp:Wv5-generated@db.example.org:5432/webapp",
        oidc=OidcSettings(
            base_url="https://auth.example.org/realms/celine",
            jwks_uri="https://auth.example.org/realms/celine/protocol/openid-connect/certs",
            client_id="svc-webapp",
            client_secret="a-real-generated-secret",
        ),
    )


@pytest.mark.usefixtures("no_oidc_env")
@pytest.mark.parametrize("env", HARDENED)
def test_hardened_refuses_every_shipped_default(env: str) -> None:
    guard = posture_guard(_shipped_defaults(env))

    assert {v.setting for v in guard.violations} == {
        "DATABASE_URL",
        "CELINE_OIDC_BASE_URL",
        "CELINE_OIDC_JWKS_URI",
    }
    with pytest.raises(InsecureConfiguration, match="DATABASE_URL"):
        guard.enforce()


@pytest.mark.usefixtures("no_oidc_env")
@pytest.mark.parametrize("env", HARDENED)
def test_hardened_refuses_each_default_on_its_own(env: str) -> None:
    good = _deployed(env)
    cases = {
        "DATABASE_URL": good.model_copy(update={"database_url": DEV_DATABASE_URL}),
        "CELINE_OIDC_CLIENT_SECRET": good.model_copy(
            update={"oidc": good.oidc.model_copy(update={"client_secret": "svc-webapp"})}
        ),
        "CELINE_OIDC_BASE_URL": good.model_copy(
            update={"oidc": OidcSettings(**good.oidc.model_dump(exclude={"base_url"}))}
        ),
        "CELINE_OIDC_JWKS_URI": good.model_copy(
            update={"oidc": OidcSettings(**good.oidc.model_dump(exclude={"jwks_uri"}))}
        ),
    }
    for setting, candidate in cases.items():
        guard = posture_guard(candidate)
        assert [v.setting for v in guard.violations] == [setting]
        with pytest.raises(InsecureConfiguration, match=setting):
            guard.enforce()


@pytest.mark.parametrize("env", HARDENED)
def test_hardened_starts_with_a_real_configuration(env: str) -> None:
    guard = posture_guard(_deployed(env))

    assert guard.violations == []
    guard.enforce()


@pytest.mark.parametrize("env", HARDENED)
def test_hardened_accepts_no_client_identity(env: str) -> None:
    """The client credentials only serve nudging reminders; unset is not a violation."""
    good = _deployed(env)
    oidc = good.oidc.model_copy(update={"client_id": None, "client_secret": None})

    assert posture_guard(good.model_copy(update={"oidc": oidc})).violations == []


@pytest.mark.usefixtures("no_oidc_env")
def test_dev_starts_with_the_shipped_defaults(caplog: pytest.LogCaptureFixture) -> None:
    guard = posture_guard(_shipped_defaults("dev"))

    guard.enforce()

    assert "development setting(s) in use" in caplog.text


@pytest.mark.parametrize(
    ("celine_env", "environment", "hardened"),
    [
        ("", "", True),
        ("staging", "", True),
        ("prod", "dev", True),  # CELINE_ENV wins
        ("development", "", True),  # only the exact value relaxes
        ("", "dev", False),  # ENVIRONMENT is the fallback name
        ("DEV", "", False),
    ],
)
def test_only_dev_relaxes(celine_env: str, environment: str, hardened: bool) -> None:
    result = Settings(_env_file=None, celine_env=celine_env, environment=environment)

    assert posture_guard(result).hardened is hardened


@pytest.mark.parametrize("env", HARDENED)
def test_create_app_refuses_before_the_database_is_opened(monkeypatch, env: str) -> None:
    """The suite's own settings carry a weak database password, so the factory refuses."""
    monkeypatch.setattr(settings, "celine_env", env)
    monkeypatch.setattr(settings, "environment", "")

    with pytest.raises(InsecureConfiguration, match="DATABASE_URL"):
        main_module.create_app()
