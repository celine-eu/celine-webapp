"""Shared fixtures.

**No test here reaches a live service.** This repository is a backend-for-frontend: it
needs PostgreSQL for its own small amount of state, Keycloak to verify the caller's token,
and four upstream APIs through `celine-sdk`. All of them are replaced here, each at the
narrowest boundary that still exercises this repository's own code.

Two of those seams are subtler than they look, and both were live defects
(`.agents/plans/the-suite-is-red.md`):

**Identity is verified for real.** Tokens are genuinely signed with a throwaway RSA key and
genuinely verified — signature, `exp`, `nbf` and `iss` all in force. The only thing stubbed
is the JWKS *fetch*, which would otherwise need a running Keycloak. Overriding
`get_user_from_request` instead would be easier and worthless: it proves the override was
called, and can never catch a token this service should have rejected.

**The database is per-test, on a temp file, with `NullPool`.** `db/session.py` builds
`async_engine` as a module global at import time, so its pooled connections outlive the
event loop that created them. `TestClient` runs the app in its own thread with its own
loop, so any connection shared between a fixture and the app crosses loops — which is what
an in-memory database on a `StaticPool` would force. A temp file with no pooling means every
connection is opened and closed on the loop that uses it. For the same reason `init_db` is
redirected at the test engine rather than disabled: schema creation then happens on the
app's loop, where every later query also runs.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Must run before the first `celine.webapp` import. `settings.py` builds its
# `Settings()` at import time and `db/session.py` builds both engines from it, so by
# collection time the wiring has already happened and no fixture can undo it.
#
# The URL keeps the `+asyncpg` driver because `db/session.py` derives its Alembic-only
# sync engine by string-replacing that exact substring. Nothing ever connects to it:
# every session in a test comes from the per-test engine below.
# ---------------------------------------------------------------------------
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@127.0.0.1:1/test"
os.environ.setdefault("DATA_SHARING_ENABLED", "false")

import time  # noqa: E402
import uuid  # noqa: E402
from typing import Any, Iterator  # noqa: E402

import jwt  # noqa: E402
import pytest  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool  # noqa: E402

from celine.sdk.auth import jwt as sdk_jwt  # noqa: E402
from celine.webapp import main as main_module  # noqa: E402
from celine.webapp.api.deps import (  # noqa: E402
    get_dt_client,
    get_flexibility_client,
    get_nudging_client,
    get_registry_client,
)
from celine.webapp.db import Base, get_db  # noqa: E402
from celine.webapp.main import create_app  # noqa: E402
from celine.webapp.settings import settings as app_settings  # noqa: E402

from tests.fakes import (  # noqa: E402
    FakeDTClient,
    FakeFlexibilityClient,
    FakeNudgingClient,
    FakeRegistryClient,
)


TEST_KEY_ID = "test-key-1"


# ─── Identity ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def signing_key() -> rsa.RSAPrivateKey:
    """One throwaway RSA key for the whole session. Generating it is not cheap."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def stub_jwks(monkeypatch: pytest.MonkeyPatch, signing_key: rsa.RSAPrivateKey) -> None:
    """Serve the test public key in place of Keycloak's JWKS endpoint.

    This is the *only* part of token handling that is faked. `JwtUser.from_token` still
    verifies the signature against this key and still enforces `iss`, `exp` and `nbf`.

    `_get_jwks_client` is `lru_cache`d in the SDK, so it is replaced rather than primed —
    a cached real client would otherwise leak between tests.
    """
    public_key = signing_key.public_key()

    class _SigningKey:
        key = public_key

    class _JwksClient:
        def get_signing_key_from_jwt(self, token: str) -> _SigningKey:
            header = jwt.get_unverified_header(token)
            if header.get("kid") != TEST_KEY_ID:
                raise jwt.PyJWKClientError(
                    f'Unable to find a signing key that matches: "{header.get("kid")}"'
                )
            return _SigningKey()

    monkeypatch.setattr(sdk_jwt, "_get_jwks_client", lambda jwks_uri: _JwksClient())


@pytest.fixture
def make_token(signing_key: rsa.RSAPrivateKey):
    """Mint a genuinely signed RS256 token.

    `iss` must match `OidcSettings.base_url`; the SDK rejects the token otherwise. No
    `aud` is set because `oidc.audience` is unset by default, which switches audience
    verification off — set both together if that ever changes.
    """
    private_pem = signing_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    def _make(
        sub: str = "test-user-123",
        email: str | None = "test@example.com",
        name: str = "Test User",
        expires_in: int = 3600,
        issuer: str | None = None,
        key_id: str = TEST_KEY_ID,
        **extra_claims: Any,
    ) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "sub": sub,
            "name": name,
            "preferred_username": email or sub,
            "iss": issuer if issuer is not None else app_settings.oidc.base_url,
            "iat": now,
            "nbf": now,
            "exp": now + expires_in,
        }
        if email is not None:
            claims["email"] = email
        claims.update(extra_claims)
        return jwt.encode(
            claims, private_pem, algorithm="RS256", headers={"kid": key_id}
        )

    return _make


@pytest.fixture
def auth_headers(make_token) -> dict[str, str]:
    """Headers carrying a valid token, in the header oauth2-proxy actually injects."""
    return {app_settings.jwt_header_name: make_token()}


# ─── Database ────────────────────────────────────────────────────────────────


@pytest.fixture
def db_url(tmp_path) -> str:
    """A SQLite database per test, on disk.

    On disk rather than in memory because in-memory SQLite is scoped to a connection:
    sharing one across the fixture and the app's thread requires a `StaticPool`, and that
    single connection would then be used from two event loops.
    """
    return f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def db_sessionmaker(db_url: str) -> async_sessionmaker[AsyncSession]:
    """A sessionmaker bound to a fresh, unpooled engine.

    `NullPool` is the point: every checkout opens a real connection and closes it when the
    session ends, so no connection is ever handed to a loop other than the one that made it.
    """
    engine = create_async_engine(db_url, poolclass=NullPool)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ─── Application ─────────────────────────────────────────────────────────────


@pytest.fixture
def fake_dt() -> FakeDTClient:
    return FakeDTClient()


@pytest.fixture
def fake_flexibility() -> FakeFlexibilityClient:
    return FakeFlexibilityClient()


@pytest.fixture
def fake_nudging() -> FakeNudgingClient:
    return FakeNudgingClient()


@pytest.fixture
def fake_registry() -> FakeRegistryClient:
    return FakeRegistryClient()


@pytest.fixture
def app(
    monkeypatch: pytest.MonkeyPatch,
    db_sessionmaker: async_sessionmaker[AsyncSession],
    fake_dt: FakeDTClient,
    fake_flexibility: FakeFlexibilityClient,
    fake_nudging: FakeNudgingClient,
    fake_registry: FakeRegistryClient,
):
    """The real application, wired to fakes at every dependency that leaves the process."""

    async def create_schema() -> None:
        engine = db_sessionmaker.kw["bind"]
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # Redirected, not disabled: this runs inside the app's lifespan, so the schema is
    # created on the same loop that later serves every request.
    monkeypatch.setattr(main_module, "init_db", create_schema)

    async def override_get_db():
        async with db_sessionmaker() as session:
            yield session

    application = create_app()
    application.dependency_overrides[get_db] = override_get_db
    application.dependency_overrides[get_dt_client] = lambda: fake_dt
    application.dependency_overrides[get_flexibility_client] = lambda: fake_flexibility
    application.dependency_overrides[get_nudging_client] = lambda: fake_nudging
    application.dependency_overrides[get_registry_client] = lambda: fake_registry

    yield application

    application.dependency_overrides.clear()


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    """A client over the real app. Entering the context manager runs the lifespan."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def lenient_client(app) -> Iterator[TestClient]:
    """A client that renders unhandled exceptions as 500 instead of re-raising them.

    `TestClient` defaults to re-raising, which is usually what you want — an exception is
    easier to read than a status code. Use this one where the *status a caller receives*
    is the thing under test, because that is what the frontend actually sees.
    """
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
