"""The two authority levels, with tokens a real local Keycloak issued.

**Opt-in, and local only.** The default suite reaches no live service (ADR-0001); this
module is skipped unless ``CELINE_WEBAPP_REAL_TOKENS=1``. It then mints tokens from the
Keycloak named by ``OidcSettings.base_url`` and verifies them against that realm's real
JWKS — nothing about identity is stubbed here. It refuses to run against any host that is
not ``*.localhost`` or a loopback address.

What it needs from the realm (the converged local dev realm provides all of it):

- the ``oauth2_proxy`` client with a direct grant (secret ``CELINE_WEBAPP_TOKEN_CLIENT_SECRET``,
  default ``oauth2_proxy``);
- a user holding the realm role ``platform-admin`` (``CELINE_WEBAPP_PLATFORM_ADMIN_USER``,
  default ``admin``);
- a user in the REC's ``admins`` organization group and nothing else
  (``CELINE_WEBAPP_ORG_ADMIN_USER``, default ``org-admin``) and one in its ``viewers``
  (``CELINE_WEBAPP_ORG_VIEWER_USER``, default ``org-viewer``); passwords equal usernames;
- the REC's organization alias (``CELINE_WEBAPP_REC_ALIAS``, default ``example_rec``).

A token that still carries a retired realm group (``groups: ["/admins", "admins"]`` and
realm role ``admin``) cannot be minted from a converged realm. Pass one minted elsewhere in
``CELINE_WEBAPP_LEGACY_GROUP_TOKEN`` to run that case; it is skipped otherwise.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx
import jwt
import pytest

from celine.webapp.settings import settings as app_settings

pytestmark = pytest.mark.skipif(
    os.environ.get("CELINE_WEBAPP_REAL_TOKENS") != "1",
    reason="real-token tests need a local Keycloak; set CELINE_WEBAPP_REAL_TOKENS=1",
)

REC = os.environ.get("CELINE_WEBAPP_REC_ALIAS", "example_rec")
# An alias no dev user is a member of: only the platform level can reach it.
OTHER_REC = "rec-nobody-is-a-member-of"
CLIENT_ID = "oauth2_proxy"
CLIENT_SECRET = os.environ.get("CELINE_WEBAPP_TOKEN_CLIENT_SECRET", "oauth2_proxy")


def _local_issuer() -> str:
    issuer = app_settings.oidc.base_url.rstrip("/")
    host = urlparse(issuer).hostname or ""
    if not (host == "localhost" or host.endswith(".localhost") or host in {"127.0.0.1", "::1"}):
        pytest.fail(f"refusing to mint tokens from a non-local issuer: {issuer}")
    return issuer


def _mint(username: str) -> str:
    response = httpx.post(
        f"{_local_issuer()}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "username": username,
            "password": username,
            "scope": "openid email profile organization:*",
        },
        timeout=10,
    )
    assert response.status_code == 200, f"{username}: {response.status_code} {response.text}"
    return response.json()["access_token"]


@pytest.fixture(autouse=True)
def stub_jwks() -> None:
    """Overrides the suite-wide JWKS stub: tokens here verify against the realm's real keys."""


@pytest.fixture(scope="module")
def tokens() -> dict[str, str]:
    return {
        "platform_admin": _mint(os.environ.get("CELINE_WEBAPP_PLATFORM_ADMIN_USER", "admin")),
        "org_admin": _mint(os.environ.get("CELINE_WEBAPP_ORG_ADMIN_USER", "org-admin")),
        "org_viewer": _mint(os.environ.get("CELINE_WEBAPP_ORG_VIEWER_USER", "org-viewer")),
    }


def _claims(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False})


def _status(client, token: str, community: str) -> int:
    return client.get(
        f"/api/feedback/manager/{community}",
        headers={app_settings.jwt_header_name: token},
    ).status_code


def test_the_tokens_have_the_shape_this_module_relies_on(tokens) -> None:
    admin = _claims(tokens["platform_admin"])
    assert "platform-admin" in admin["realm_access"]["roles"]
    assert OTHER_REC not in (admin.get("organization") or {})

    org_admin = _claims(tokens["org_admin"])
    assert "platform-admin" not in (org_admin.get("realm_access") or {}).get("roles", [])
    assert org_admin["organization"][REC]["groups"] == ["/admins"]
    assert "community.read" in org_admin["scope"].split()

    for token in tokens.values():
        assert "groups" not in _claims(token), "the realm still emits a top-level groups claim"


def test_a_platform_admin_reaches_any_rec(client, tokens) -> None:
    assert _status(client, tokens["platform_admin"], REC) == 200
    assert _status(client, tokens["platform_admin"], OTHER_REC) == 200


def test_an_organisation_admin_is_not_a_platform_admin(client, tokens) -> None:
    assert _status(client, tokens["org_admin"], REC) == 200
    assert _status(client, tokens["org_admin"], OTHER_REC) == 403


def test_an_organisation_viewer_is_not_a_manager(client, tokens) -> None:
    assert _status(client, tokens["org_viewer"], REC) == 403


def test_a_retired_realm_group_grants_nothing(client) -> None:
    token = os.environ.get("CELINE_WEBAPP_LEGACY_GROUP_TOKEN")
    if not token:
        pytest.skip("no CELINE_WEBAPP_LEGACY_GROUP_TOKEN given")
    claims = _claims(token)
    assert "/admins" in claims.get("groups", []) or "admins" in claims.get("groups", [])
    assert "platform-admin" not in (claims.get("realm_access") or {}).get("roles", [])
    assert _status(client, token, OTHER_REC) == 403
    member_of = set((claims.get("organization") or {}).keys())
    if REC not in member_of:
        assert _status(client, token, REC) == 403
