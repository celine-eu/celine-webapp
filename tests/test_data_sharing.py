"""A member's own data-sharing decisions.

The onboarding wizard can only *grant* a sharing consent — it holds no session
after approval and no credential — so without these routes a decision could be
given and never taken back. GDPR Art. 7(3) requires withdrawal to be as easy as
giving, which makes this surface the point rather than a nicety.

Two properties the tests below pin, because both are easy to lose:

* the feature is **off by default** and the routes then do not exist, so nothing
  half-working is exposed while the dataspace is undeployed;
* a member with **no dataspace identity** is a normal state, not an error — the
  UI explains it rather than showing a failure.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from celine.webapp.services import data_sharing as service
from celine.webapp.settings import settings

@pytest.fixture
def client() -> TestClient:
    """An app with only these routes.

    Deliberately not the shared `client` fixture. The original reason — that it opened a
    real database connection — stopped being true on 2026-08-15, when the suite became
    hermetic. The remaining reason stands on its own: these routes touch no database and
    no upstream except the dataspace, so mounting the whole application would pull in
    wiring whose failure would be attributed here.
    """
    from fastapi import FastAPI

    from celine.webapp.api.data_sharing import router
    from celine.webapp.api.deps import get_user_from_request
    from celine.sdk.auth import JwtUser

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_user_from_request] = lambda: JwtUser(
        sub="test-user-123", email="test@example.com", name="Test User"
    )
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth_headers() -> dict:
    """The routes read identity from the dependency, not the header."""
    return {}


OFFERS = [
    {
        "id": "household-energy-flexibility",
        "purpose": "FlexibilityResearch",
        "requires_consent": True,
        "consent_text_version": "1.0",
    },
    {
        "id": "grid-operations-planning",
        "purpose": "EnergyCommunityOperation",
        "requires_consent": False,
        "consent_text_version": "1.0",
    },
]

CREDENTIAL = service.SubjectCredential(
    subject_id="did:web:users.example:email-abc", vc_jws="jws-token"
)


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "data_sharing_enabled", True)
    monkeypatch.setattr(settings, "identity_registry_url", "http://ir:30005")
    monkeypatch.setattr(settings, "ds_connector_url", "http://connector:30001")


@pytest.fixture
def stub_service(monkeypatch):
    """Stand in for the dataspace, recording what was asked of it."""
    calls: list = []

    async def _resolve(email):
        return CREDENTIAL

    async def _offers():
        return list(OFFERS)

    async def _decisions(credential):
        return [
            {
                "offer_id": "household-energy-flexibility",
                "status": "granted",
                "decided_at": "2026-07-01T10:00:00Z",
                "legal_basis": {"consent_text_version": "1.0", "source": "onboarding"},
            }
        ]

    async def _set(credential, offer_id, *, enabled):
        calls.append((credential.subject_id, offer_id, enabled))
        return {}

    async def _history(credential):
        return [{"event_type": "ConsentGranted", "offer_id": "household-energy-flexibility"}]

    monkeypatch.setattr(service, "resolve_subject", _resolve)
    monkeypatch.setattr(service, "list_offers", _offers)
    monkeypatch.setattr(service, "list_decisions", _decisions)
    monkeypatch.setattr(service, "set_decision", _set)
    monkeypatch.setattr(service, "list_history", _history)
    return calls


# ── the feature gate ──────────────────────────────────────────────────────────


class TestFeatureGate:
    def test_disabled_by_default(self):
        """A sharing screen that cannot answer is worse than no screen: a member
        would record a decision that takes effect nowhere."""
        assert settings.data_sharing_enabled is False

    def test_routes_do_not_exist_when_disabled(
        self, client: TestClient, auth_headers: dict, monkeypatch
    ):
        monkeypatch.setattr(settings, "data_sharing_enabled", False)

        for path in ("/api/data-sharing", "/api/data-sharing/history"):
            assert client.get(path, headers=auth_headers).status_code == 404

    def test_enabled_but_unconfigured_stays_off(self, monkeypatch):
        """The flag alone is not enough — without somewhere to resolve a
        credential and record a decision there is nothing to show."""
        monkeypatch.setattr(settings, "data_sharing_enabled", True)
        monkeypatch.setattr(settings, "identity_registry_url", None)

        assert settings.data_sharing_ready is False

    def test_me_advertises_the_flag(self):
        """`/api/me` carries the flag so the UI can hide the section rather than
        link to a 404. Asserted on the schema: the route itself needs a database
        this suite cannot start."""
        from celine.webapp.api.schemas import MeResponse

        assert "data_sharing_enabled" in MeResponse.model_fields


# ── reading decisions ─────────────────────────────────────────────────────────


class TestReadDecisions:
    def test_offers_are_merged_with_the_members_decisions(
        self, client: TestClient, auth_headers: dict, enabled, stub_service
    ):
        body = client.get("/api/data-sharing", headers=auth_headers).json()

        assert body["has_identity"] is True
        by_id = {o["id"]: o for o in body["offers"]}
        assert by_id["household-energy-flexibility"]["granted"] is True
        assert by_id["grid-operations-planning"]["granted"] is False

    def test_the_evidence_record_is_surfaced(
        self, client: TestClient, auth_headers: dict, enabled, stub_service
    ):
        """Codes and hashes only — the record of what was shown when the decision
        was made, which is what makes it defensible later."""
        body = client.get("/api/data-sharing", headers=auth_headers).json()
        granted = next(o for o in body["offers"] if o["granted"])

        assert granted["evidence"]["consent_text_version"] == "1.0"

    def test_contract_based_offers_are_still_listed(
        self, client: TestClient, auth_headers: dict, enabled, stub_service
    ):
        """Disclosed, not hidden. The member is entitled to know it happens; the
        UI is what withholds the toggle."""
        body = client.get("/api/data-sharing", headers=auth_headers).json()

        contract = next(
            o for o in body["offers"] if o["id"] == "grid-operations-planning"
        )
        assert contract["requires_consent"] is False

    def test_no_dataspace_identity_is_not_an_error(
        self, client: TestClient, auth_headers: dict, enabled, monkeypatch
    ):
        """Normal for a participant enabled before the integration existed."""

        async def _none(email):
            raise service.NoDataspaceIdentity(email)

        monkeypatch.setattr(service, "resolve_subject", _none)

        response = client.get("/api/data-sharing", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == {"has_identity": False, "offers": []}

    def test_an_unreachable_dataspace_is_a_503(
        self, client: TestClient, auth_headers: dict, enabled, monkeypatch
    ):
        """Distinct from the feature being off, and from having no identity —
        this one is worth retrying."""

        async def _down(email):
            raise service.DataSharingUnavailable("connector down")

        monkeypatch.setattr(service, "resolve_subject", _down)

        assert client.get("/api/data-sharing", headers=auth_headers).status_code == 503


# ── changing them ─────────────────────────────────────────────────────────────


class TestChangeDecisions:
    def test_withdrawing(
        self, client: TestClient, auth_headers: dict, enabled, stub_service
    ):
        """The reason this surface exists at all."""
        response = client.post(
            "/api/data-sharing/household-energy-flexibility",
            json={"enabled": False},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert stub_service == [(CREDENTIAL.subject_id, "household-energy-flexibility", False)]

    def test_granting(
        self, client: TestClient, auth_headers: dict, enabled, stub_service
    ):
        client.post(
            "/api/data-sharing/household-energy-flexibility",
            json={"enabled": True},
            headers=auth_headers,
        )

        assert stub_service[0][2] is True

    def test_a_contract_offer_cannot_be_toggled(
        self, client: TestClient, auth_headers: dict, enabled, stub_service, monkeypatch
    ):
        """Presenting a choice that does not exist is what invalidates consent,
        so the connector refuses and this surfaces the refusal."""

        async def _refuse(credential, offer_id, *, enabled):
            raise ValueError("This offer is not consent-based")

        monkeypatch.setattr(service, "set_decision", _refuse)

        response = client.post(
            "/api/data-sharing/grid-operations-planning",
            json={"enabled": True},
            headers=auth_headers,
        )

        assert response.status_code == 409

    def test_no_identity_cannot_decide(
        self, client: TestClient, auth_headers: dict, enabled, monkeypatch
    ):
        async def _none(email):
            raise service.NoDataspaceIdentity(email)

        monkeypatch.setattr(service, "resolve_subject", _none)

        response = client.post(
            "/api/data-sharing/household-energy-flexibility",
            json={"enabled": True},
            headers=auth_headers,
        )

        assert response.status_code == 409


# ── history ───────────────────────────────────────────────────────────────────


class TestHistory:
    def test_returns_the_members_own_events(
        self, client: TestClient, auth_headers: dict, enabled, stub_service
    ):
        body = client.get("/api/data-sharing/history", headers=auth_headers).json()

        assert body["has_identity"] is True
        assert body["events"][0]["event_type"] == "ConsentGranted"

    def test_absent_provenance_does_not_break_the_page(
        self, client: TestClient, auth_headers: dict, enabled, stub_service, monkeypatch
    ):
        """The decisions stand without it; failing here would make the whole
        surface unusable for a detail."""

        async def _empty(credential):
            return []

        monkeypatch.setattr(service, "list_history", _empty)

        response = client.get("/api/data-sharing/history", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["events"] == []


# ── credential selection ──────────────────────────────────────────────────────


class TestCredentialSelection:
    """One person legitimately holds several credentials.

    Reading the singular `vc_jws` takes whichever was issued last, which for
    somebody who also holds a consumer credential is the wrong one — and the
    connector would then refuse an operation the member is entitled to perform.
    """

    async def test_picks_the_data_subject_credential(self, monkeypatch):
        import httpx

        payload = {
            "did": "did:web:users.example:email-abc",
            "role": "ConsumerUser",
            "vc_jws": "consumer-jws",
            "credentials": [
                {"role": "ConsumerUser", "vc_jws": "consumer-jws"},
                {"role": "DataSubject", "vc_jws": "subject-jws"},
            ],
        }

        monkeypatch.setattr(settings, "identity_registry_url", "http://ir:30005")
        _patch_resolve(monkeypatch, httpx, payload)

        credential = await service.resolve_subject("a@example.com")
        assert credential.vc_jws == "subject-jws"

    async def test_no_data_subject_credential_means_no_identity(self, monkeypatch):
        import httpx

        payload = {
            "did": "did:web:users.example:email-abc",
            "credentials": [{"role": "ConsumerUser", "vc_jws": "consumer-jws"}],
        }

        monkeypatch.setattr(settings, "identity_registry_url", "http://ir:30005")
        _patch_resolve(monkeypatch, httpx, payload)

        with pytest.raises(service.NoDataspaceIdentity):
            await service.resolve_subject("a@example.com")


def _patch_resolve(monkeypatch, httpx, payload):
    """Serve one canned /users/resolve response, with a stubbed service token."""

    class _Token:
        access_token = "svc-token"

    class _Provider:
        async def get_token(self):
            return _Token()

    monkeypatch.setattr(service, "_resolve_token_provider", lambda: _Provider())

    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=payload)
    )
    original = httpx.AsyncClient

    def factory(**kwargs):
        kwargs.pop("transport", None)
        return original(transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
