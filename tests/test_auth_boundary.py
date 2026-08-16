"""What this service accepts as an identity, and what it must not.

This service establishes no identity of its own: it is deployed same-origin behind
oauth2-proxy and *reads* the token that arrives. That makes the read the security
boundary, and the only one this repository owns.

These tests exist because the boundary was previously unexercised in the worst possible
way. The old `auth_headers` fixture minted an `{"alg": "none"}` token with the literal
signature `test-signature`; every authenticated test failed 401 as a result, and the
suite had been red long enough that the failure read as noise rather than as the correct
rejection of a forged token.

So the tokens here are genuinely signed and genuinely verified. Only the JWKS *fetch* is
stubbed — see `tests/conftest.py`. A suite that overrode `get_user_from_request` instead
would pass just as easily with the verification deleted.
"""

from __future__ import annotations

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from celine.webapp.settings import settings as app_settings


HEADER = app_settings.jwt_header_name


def test_no_token_is_rejected(client: TestClient) -> None:
    assert client.get("/api/me").status_code == 401


def test_a_valid_token_is_accepted(client: TestClient, auth_headers: dict) -> None:
    response = client.get("/api/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["user"]["sub"] == "test-user-123"


def test_an_unsigned_token_is_rejected(client: TestClient, make_token) -> None:
    """The exact forgery the old fixture produced: `alg: none`, no key id.

    It must be rejected. That it *was* rejected is the reason seven tests were red.
    """
    import base64
    import json

    def _segment(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    forged = f"{_segment({'alg': 'none'})}.{_segment({'sub': 'test-user-123'})}.sig"

    assert client.get("/api/me", headers={HEADER: forged}).status_code == 401


def test_a_token_signed_by_the_wrong_key_is_rejected(client: TestClient) -> None:
    """A well-formed token carrying the expected key id, signed by a key we do not trust."""
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = attacker_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    import time

    now = int(time.time())
    forged = jwt.encode(
        {
            "sub": "test-user-123",
            "iss": app_settings.oidc.base_url,
            "iat": now,
            "exp": now + 3600,
        },
        pem,
        algorithm="RS256",
        headers={"kid": "test-key-1"},
    )

    assert client.get("/api/me", headers={HEADER: forged}).status_code == 401


def test_an_expired_token_is_rejected(client: TestClient, make_token) -> None:
    """`exp` is checked with 30 seconds of leeway, so this is well past it."""
    expired = make_token(expires_in=-600)
    assert client.get("/api/me", headers={HEADER: expired}).status_code == 401


def test_a_token_from_another_issuer_is_rejected(client: TestClient, make_token) -> None:
    other = make_token(issuer="http://keycloak.example.invalid/realms/other")
    assert client.get("/api/me", headers={HEADER: other}).status_code == 401


def test_an_unknown_key_id_is_rejected(client: TestClient, make_token) -> None:
    assert client.get(
        "/api/me", headers={HEADER: make_token(key_id="some-other-key")}
    ).status_code == 401


def test_a_bearer_authorization_header_is_accepted(
    client: TestClient, make_token
) -> None:
    """`_extract_token` falls back to `Authorization: Bearer` when the proxy header is absent.

    Worth pinning: it is the path used by anything calling the API outside the proxy.
    """
    token = make_token()
    response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["user"]["sub"] == "test-user-123"


def test_identity_comes_from_the_token_not_a_header(
    client: TestClient, make_token
) -> None:
    """Claims are read from the verified token, never from the surrounding headers."""
    token = make_token(sub="the-real-subject", email="real@example.com")
    response = client.get(
        "/api/me",
        headers={
            HEADER: token,
            "x-auth-request-user": "someone-else",
            "x-auth-request-email": "someone-else@example.com",
        },
    )
    assert response.status_code == 200
    assert response.json()["user"]["sub"] == "the-real-subject"
    assert response.json()["user"]["email"] == "real@example.com"
