"""The seam to onboarding: the caller's own token, and nothing else.

The client itself is `celine.sdk.onboarding.OnboardingClient`, and its behaviour
— the paths, the schemas, the refusals — is tested in `celine-sdk`. What belongs
here is the wiring: this service builds that client per request, from the
caller's token and the configured URL, and refuses rather than improvises when
either is missing.

The property worth pinning is that **no service account exists**. A privileged
token here would let this service act on somebody else's consent, which is the
one thing that would make a recorded decision worthless.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from celine.sdk.onboarding import OnboardingClient
from celine.webapp.api.deps import OnboardingDep
from celine.webapp.settings import settings


@pytest.fixture
def sent(mock_upstream_http) -> list[httpx.Request]:
    """Record what left this service, and answer a valid status document."""
    return mock_upstream_http(
        lambda request: httpx.Response(
            200, json={"has_identity": True, "state": "ok", "offers": []}
        )
    )


@pytest.fixture
def probe_client() -> TestClient:
    """One route, whose only job is to resolve the dependency and call it."""
    app = FastAPI()

    @app.get("/probe")
    async def probe(onboarding: OnboardingDep):
        answer = await onboarding.get_data_sharing()
        return {"has_identity": answer.has_identity}

    return TestClient(app, raise_server_exceptions=False)


class TestDependency:
    def test_the_dependency_resolves_and_answers(
        self, probe_client, auth_headers, sent
    ):
        """End to end through the real wrapper and the real generated client —
        only the socket is replaced."""
        response = probe_client.get("/probe", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == {"has_identity": True}

    def test_forwards_the_callers_token(self, probe_client, auth_headers, sent):
        probe_client.get("/probe", headers=auth_headers)

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
        monkeypatch.setattr(settings, "onboarding_api_url", "http://onboarding:8040")

        probe_client.get("/probe", headers=auth_headers)

        assert str(sent[0].url) == "http://onboarding:8040/api/me/data-sharing"


def test_the_client_is_the_sdks():
    """A hand-written client here would drift from onboarding's contract with
    nothing to notice: this repository has no generated model to check against."""
    from celine.webapp.api import deps

    assert deps.OnboardingClient is OnboardingClient
    assert OnboardingClient.__module__.startswith("celine.sdk.")
