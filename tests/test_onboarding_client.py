"""The seam to onboarding: the caller's own token, and nothing else.

Onboarding owns the member's dataspace identity and their consent rows. This
service reaches it as a proxy, so the two properties worth pinning are the ones
that would be easy to lose in a later change:

* **the member's token is forwarded, and no service account exists** — a
  privileged token here would let this service act on somebody else's consent;
* **the status onboarding answers with survives** — a proxy that flattened 409
  into "unavailable" would turn "this offer cannot be toggled" into "try again
  later".
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from celine.webapp.api.deps import OnboardingDep
from celine.webapp.services import onboarding as module
from celine.webapp.services.onboarding import OnboardingClient, OnboardingUnavailable
from celine.webapp.settings import settings


@pytest.fixture
def sent(monkeypatch) -> list[httpx.Request]:
    """Record what left this service, and answer 200."""
    recorded: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(request)
        return httpx.Response(200, json={"ok": True})

    _install(monkeypatch, handler)
    return recorded


def _install(monkeypatch, handler) -> None:
    """Give the client a transport that answers instead of dialling out."""
    real = httpx.AsyncClient

    def factory(**kwargs):
        return real(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(module.httpx, "AsyncClient", factory)


@pytest.fixture
def probe_client() -> TestClient:
    """One route, whose only job is to resolve the dependency and call it."""
    app = FastAPI()

    @app.get("/probe")
    async def probe(onboarding: OnboardingDep):
        response = await onboarding.get("/api/anything")
        return {"status": response.status_code, "base_url": onboarding.base_url}

    return TestClient(app, raise_server_exceptions=False)


# ── the dependency ────────────────────────────────────────────────────────────


class TestDependency:
    def test_forwards_the_callers_token(self, probe_client, auth_headers, sent):
        response = probe_client.get("/probe", headers=auth_headers)

        assert response.status_code == 200
        token = auth_headers[settings.jwt_header_name]
        assert [r.headers["authorization"] for r in sent] == [f"Bearer {token}"]

    def test_no_token_is_401(self, probe_client, sent):
        assert probe_client.get("/probe").status_code == 401
        assert sent == []

    def test_unconfigured_is_503(self, probe_client, auth_headers, sent, monkeypatch):
        monkeypatch.setattr(settings, "onboarding_api_url", None)

        response = probe_client.get("/probe", headers=auth_headers)

        assert response.status_code == 503
        assert sent == []

    def test_uses_the_configured_base_url(
        self, probe_client, auth_headers, sent, monkeypatch
    ):
        monkeypatch.setattr(settings, "onboarding_api_url", "http://onboarding:8040/")

        response = probe_client.get("/probe", headers=auth_headers)

        assert response.json()["base_url"] == "http://onboarding:8040"
        assert str(sent[0].url) == "http://onboarding:8040/api/anything"


# ── the client ────────────────────────────────────────────────────────────────


class TestClientBehaviour:
    async def test_a_refusal_is_returned_not_raised(self, monkeypatch):
        """409 is onboarding's answer about the offer, not about its health."""
        _install(monkeypatch, lambda request: httpx.Response(409, json={"detail": "no"}))

        response = await OnboardingClient("http://onboarding:8040", "tok").post(
            "/api/me/data-sharing/x", json={"enabled": True}
        )

        assert response.status_code == 409

    async def test_transport_failure_is_onboarding_unavailable(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        _install(monkeypatch, handler)

        with pytest.raises(OnboardingUnavailable):
            await OnboardingClient("http://onboarding:8040", "tok").get("/api/anything")

    async def test_caller_headers_do_not_displace_the_token(self, monkeypatch, sent):
        await OnboardingClient("http://onboarding:8040", "tok").get(
            "/api/anything", headers={"accept-language": "it"}
        )

        assert sent[0].headers["authorization"] == "Bearer tok"
        assert sent[0].headers["accept-language"] == "it"
