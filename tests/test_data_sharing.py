"""A member's own data-sharing decisions, now served by proxy.

The decisions, the credential and the merge live in `../onboarding`. What is
left here is the seam the frontend talks to, and these tests are what makes the
relocation invisible to it: **the paths and the response shape did not change**,
and neither did the two properties that matter.

* the feature is **off by default** and the routes then do not exist, so nothing
  half-working is exposed while the dataspace is undeployed;
* a member with **no dataspace identity** is a normal state, not an error — and
  `state` now says which normal state, because "your community does not take
  part" and "you have no credential yet" used to get the same sentence.

The stub below is onboarding's HTTP surface, not this service's own functions:
what is worth pinning is the request that leaves here — the path, the body, and
the member's own token on it — because that is the half a future change could
break without any test noticing.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from celine.webapp.db.models import Base, UserOnboardingView
from celine.webapp.services import data_sharing as service
from celine.webapp.services import onboarding as onboarding_module
from celine.webapp.services.onboarding import OnboardingClient
from celine.webapp.settings import settings

USER_ID = "test-user-123"


OFFERS = [
    {
        "id": "household-energy-flexibility",
        "purpose": "FlexibilityResearch",
        "requires_consent": True,
        "consent_text_version": "1.0",
        "granted": True,
        "evidence": {"consent_text_version": "1.0", "source": "onboarding"},
        "decided_at": "2026-07-01T10:00:00Z",
    },
    {
        "id": "grid-operations-planning",
        "purpose": "EnergyCommunityOperation",
        "requires_consent": False,
        "granted": False,
        "evidence": None,
        "decided_at": None,
    },
]

STATUS_OK = {"has_identity": True, "state": "ok", "offers": OFFERS}
HISTORY_OK = {
    "has_identity": True,
    "state": "ok",
    "events": [
        {"event_type": "ConsentGranted", "offer_id": "household-energy-flexibility"}
    ],
}

TOKEN = "member-jwt"


class FakeOnboarding:
    """Onboarding's `/api/me/data-sharing`, and a record of what was asked of it."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.answers: dict[str, httpx.Response] = {}
        self.unreachable = False

    def answer(self, path: str, response: httpx.Response) -> None:
        self.answers[path] = response

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.unreachable:
            raise httpx.ConnectError("refused", request=request)
        canned = self.answers.get(request.url.path)
        if canned is not None:
            return canned
        if request.url.path.endswith("/history"):
            return httpx.Response(200, json=HISTORY_OK)
        return httpx.Response(200, json=STATUS_OK)

    @property
    def paths(self) -> list[str]:
        return [r.url.path for r in self.requests]


@pytest.fixture
def onboarding(monkeypatch) -> FakeOnboarding:
    fake = FakeOnboarding()
    real = httpx.AsyncClient

    def factory(**kwargs):
        return real(transport=httpx.MockTransport(fake.handle), **kwargs)

    monkeypatch.setattr(onboarding_module.httpx, "AsyncClient", factory)
    return fake


@pytest.fixture
def client(onboarding: FakeOnboarding, db_sessionmaker) -> TestClient:
    """An app with only these routes, and a database.

    Deliberately not the shared `client` fixture: these routes reach one upstream
    and one table, so mounting the whole application would pull in wiring whose
    failure would be attributed here. The database is real — the banner is read
    out of `user_onboarding_views`, and stubbing that would test the stub.

    Identity is overridden, the onboarding client is not: the request that
    leaves this service is the thing under test.
    """
    from celine.sdk.auth import JwtUser

    from celine.webapp.api.data_sharing import router
    from celine.webapp.api.deps import get_onboarding_client, get_user_from_request
    from celine.webapp.db import get_db

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        engine = db_sessionmaker.kw["bind"]
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield

    async def override_get_db():
        async with db_sessionmaker() as session:
            yield session

    app = FastAPI(lifespan=lifespan)
    app.include_router(router)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_user_from_request] = lambda: JwtUser(
        sub=USER_ID, email="test@example.com", name="Test User"
    )
    app.dependency_overrides[get_onboarding_client] = lambda: OnboardingClient(
        "http://onboarding:8040", TOKEN
    )
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def dismissed(db_sessionmaker):
    """Record a dismissal of the banner, as `POST /api/onboarding/seen` would."""

    def _dismiss(*, days_ago: int = 0) -> None:
        async def _write() -> None:
            async with db_sessionmaker() as session:
                session.add(
                    UserOnboardingView(
                        user_id=USER_ID,
                        page_key=service.PAGE_KEY,
                        seen_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
                    )
                )
                await session.commit()

        asyncio.run(_write())

    return _dismiss


@pytest.fixture
def auth_headers() -> dict:
    """The routes read identity from the dependency, not the header."""
    return {}


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "data_sharing_enabled", True)
    monkeypatch.setattr(settings, "onboarding_api_url", "http://onboarding:8040")


# ── the feature gate ──────────────────────────────────────────────────────────


class TestFeatureGate:
    def test_disabled_by_default(self):
        """A sharing screen that cannot answer is worse than no screen: a member
        would record a decision that takes effect nowhere."""
        assert settings.data_sharing_enabled is False

    def test_routes_do_not_exist_when_disabled(
        self, client: TestClient, auth_headers: dict, onboarding, monkeypatch
    ):
        monkeypatch.setattr(settings, "data_sharing_enabled", False)

        for path in ("/api/data-sharing", "/api/data-sharing/history"):
            assert client.get(path, headers=auth_headers).status_code == 404

        assert onboarding.requests == []

    def test_enabled_but_unconfigured_stays_off(self, monkeypatch):
        """The flag alone is not enough — with nowhere to send the decision
        there is nothing to show."""
        monkeypatch.setattr(settings, "data_sharing_enabled", True)
        monkeypatch.setattr(settings, "onboarding_api_url", None)

        assert settings.data_sharing_ready is False

    def test_me_advertises_the_flag(self):
        """`/api/me` carries the flag so the UI can hide the section rather than
        link to a 404. Asserted on the schema: the route itself needs a database
        this suite cannot start."""
        from celine.webapp.api.schemas import MeResponse

        assert "data_sharing_enabled" in MeResponse.model_fields


# ── what leaves this service ──────────────────────────────────────────────────


class TestTheRequestUpstream:
    def test_the_members_own_token_goes_up_and_nothing_else(
        self, client: TestClient, auth_headers: dict, enabled, onboarding
    ):
        """No service account, here or ever. A token that could act for somebody
        else would make the recorded decision worthless."""
        client.get("/api/data-sharing", headers=auth_headers)

        assert onboarding.requests[0].headers["authorization"] == f"Bearer {TOKEN}"

    def test_each_route_calls_its_own_path(
        self, client: TestClient, auth_headers: dict, enabled, onboarding
    ):
        client.get("/api/data-sharing", headers=auth_headers)
        client.get("/api/data-sharing/history", headers=auth_headers)
        client.post(
            "/api/data-sharing/household-energy-flexibility",
            json={"enabled": False},
            headers=auth_headers,
        )

        assert onboarding.paths == [
            "/api/me/data-sharing",
            "/api/me/data-sharing/history",
            "/api/me/data-sharing/household-energy-flexibility",
        ]


# ── reading decisions ─────────────────────────────────────────────────────────


class TestReadDecisions:
    def test_offers_and_decisions_are_passed_through(
        self, client: TestClient, auth_headers: dict, enabled, onboarding
    ):
        body = client.get("/api/data-sharing", headers=auth_headers).json()

        assert body["has_identity"] is True
        by_id = {o["id"]: o for o in body["offers"]}
        assert by_id["household-energy-flexibility"]["granted"] is True
        assert by_id["grid-operations-planning"]["granted"] is False

    def test_the_evidence_record_is_surfaced(
        self, client: TestClient, auth_headers: dict, enabled, onboarding
    ):
        """Codes and hashes only — the record of what was shown when the decision
        was made, which is what makes it defensible later."""
        body = client.get("/api/data-sharing", headers=auth_headers).json()
        granted = next(o for o in body["offers"] if o["granted"])

        assert granted["evidence"]["consent_text_version"] == "1.0"

    def test_contract_based_offers_are_still_listed(
        self, client: TestClient, auth_headers: dict, enabled, onboarding
    ):
        """Disclosed, not hidden. The member is entitled to know it happens; the
        UI is what withholds the toggle."""
        body = client.get("/api/data-sharing", headers=auth_headers).json()

        contract = next(
            o for o in body["offers"] if o["id"] == "grid-operations-planning"
        )
        assert contract["requires_consent"] is False

    def test_no_dataspace_identity_is_not_an_error(
        self, client: TestClient, auth_headers: dict, enabled, onboarding
    ):
        """Normal for a preregistered member who holds no credential yet."""
        onboarding.answer(
            "/api/me/data-sharing",
            httpx.Response(
                200, json={"has_identity": False, "state": "no_identity", "offers": []}
            ),
        )

        response = client.get("/api/data-sharing", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == {
            "has_identity": False,
            "state": "no_identity",
            "offers": [],
            "asked": False,
            "review_due": False,
        }

    def test_a_community_outside_the_dataspace_is_a_different_state(
        self, client: TestClient, auth_headers: dict, enabled, onboarding
    ):
        """The distinction the state field exists for: nothing to decide, and
        nothing that provisioning could fix."""
        onboarding.answer(
            "/api/me/data-sharing",
            httpx.Response(
                200, json={"has_identity": False, "state": "no_dataspace", "offers": []}
            ),
        )

        body = client.get("/api/data-sharing", headers=auth_headers).json()

        assert body["state"] == "no_dataspace"

    def test_an_unreachable_dataspace_is_a_503(
        self, client: TestClient, auth_headers: dict, enabled, onboarding
    ):
        """Onboarding says the dataspace is down; this is worth retrying, and is
        distinct both from the feature being off and from having no identity."""
        onboarding.answer(
            "/api/me/data-sharing",
            httpx.Response(503, json={"detail": "Connector unreachable"}),
        )

        response = client.get("/api/data-sharing", headers=auth_headers)

        assert response.status_code == 503
        assert response.json()["detail"] == "Connector unreachable"

    def test_unreachable_onboarding_is_a_503(
        self, client: TestClient, auth_headers: dict, enabled, onboarding
    ):
        """Onboarding itself being down, rather than the dataspace behind it.
        The member sees the same retryable answer either way."""
        onboarding.unreachable = True

        assert client.get("/api/data-sharing", headers=auth_headers).status_code == 503

    def test_a_missing_upstream_surface_is_not_the_feature_gate(
        self, client: TestClient, auth_headers: dict, enabled, onboarding
    ):
        """404 here means "switched off". An onboarding that answers 404 means
        this service is calling a route that moved — a deployment fault, and the
        member must not be told the feature does not exist."""
        onboarding.answer("/api/me/data-sharing", httpx.Response(404))

        assert client.get("/api/data-sharing", headers=auth_headers).status_code == 502


# ── changing them ─────────────────────────────────────────────────────────────


class TestChangeDecisions:
    def test_withdrawing(
        self, client: TestClient, auth_headers: dict, enabled, onboarding
    ):
        """The reason this surface exists at all."""
        response = client.post(
            "/api/data-sharing/household-energy-flexibility",
            json={"enabled": False},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert onboarding.requests[0].read() == b'{"enabled":false}'

    def test_granting(
        self, client: TestClient, auth_headers: dict, enabled, onboarding
    ):
        client.post(
            "/api/data-sharing/household-energy-flexibility",
            json={"enabled": True},
            headers=auth_headers,
        )

        assert onboarding.requests[0].read() == b'{"enabled":true}'

    def test_a_contract_offer_cannot_be_toggled(
        self, client: TestClient, auth_headers: dict, enabled, onboarding
    ):
        """Presenting a choice that does not exist is what invalidates consent,
        so onboarding refuses and the reason it gave is forwarded."""
        onboarding.answer(
            "/api/me/data-sharing/grid-operations-planning",
            httpx.Response(
                409,
                json={"detail": "grid-operations-planning is disclosed under a contract"},
            ),
        )

        response = client.post(
            "/api/data-sharing/grid-operations-planning",
            json={"enabled": True},
            headers=auth_headers,
        )

        assert response.status_code == 409
        assert "contract" in response.json()["detail"]

    def test_no_identity_cannot_decide(
        self, client: TestClient, auth_headers: dict, enabled, onboarding
    ):
        onboarding.answer(
            "/api/me/data-sharing/household-energy-flexibility",
            httpx.Response(409, json={"detail": "no_identity"}),
        )

        response = client.post(
            "/api/data-sharing/household-energy-flexibility",
            json={"enabled": True},
            headers=auth_headers,
        )

        assert response.status_code == 409
        assert response.json()["detail"] == "no_identity"


# ── history ───────────────────────────────────────────────────────────────────


class TestHistory:
    def test_returns_the_members_own_events(
        self, client: TestClient, auth_headers: dict, enabled, onboarding
    ):
        body = client.get("/api/data-sharing/history", headers=auth_headers).json()

        assert body["has_identity"] is True
        assert body["events"][0]["event_type"] == "ConsentGranted"

    def test_absent_provenance_does_not_break_the_page(
        self, client: TestClient, auth_headers: dict, enabled, onboarding
    ):
        """The decisions stand without it; failing here would make the whole
        surface unusable for a detail. Decided upstream, where the credential is."""
        onboarding.answer(
            "/api/me/data-sharing/history",
            httpx.Response(200, json={"has_identity": True, "state": "ok", "events": []}),
        )

        response = client.get("/api/data-sharing/history", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["events"] == []


# ── no credential ever comes back ─────────────────────────────────────────────


def test_the_response_shape_cannot_carry_a_credential():
    """This service holds no credential and must not learn to pass one on.

    Onboarding redacts its own; the field list here is the second lock, and the
    one a reviewer of this repository can check.
    """
    from celine.webapp.api.schemas import (
        DataSharingHistoryResponse,
        DataSharingStatusResponse,
    )

    assert set(DataSharingStatusResponse.model_fields) == {
        "has_identity",
        "state",
        "offers",
        "asked",
        "review_due",
    }
    assert set(DataSharingHistoryResponse.model_fields) == {
        "has_identity",
        "state",
        "events",
    }


# ── the prompt ────────────────────────────────────────────────────────────────


class TestThePrompt:
    """Being asked is this service's to know.

    The decisions live in onboarding, which holds no session with the member.
    Whether they have been *asked* is per-user state about this app's own UI, so
    it comes out of `user_onboarding_views` under the `data-sharing` key — the
    same table and the same route every in-app tour already uses.
    """

    def test_a_member_who_has_never_been_asked(
        self, client: TestClient, auth_headers: dict, enabled, onboarding
    ):
        """No dismissal and no decision: the first-run sequence, not the banner."""
        onboarding.answer(
            "/api/me/data-sharing",
            httpx.Response(
                200,
                json={
                    "has_identity": True,
                    "state": "ok",
                    "offers": [{"id": "a", "granted": False, "decided_at": None}],
                },
            ),
        )

        body = client.get("/api/data-sharing", headers=auth_headers).json()

        assert body["asked"] is False
        assert body["review_due"] is False

    def test_deciding_in_the_funnel_counts_as_being_asked(
        self, client: TestClient, auth_headers: dict, enabled, onboarding
    ):
        """Somebody who consented during onboarding has been asked. Showing them
        a first-run wizard would be absurd, and no dismissal was ever recorded
        here for them."""
        body = client.get("/api/data-sharing", headers=auth_headers).json()

        assert body["asked"] is True

    def test_dismissing_counts_as_being_asked(
        self, client: TestClient, auth_headers: dict, enabled, onboarding, dismissed
    ):
        """A member who closed the banner without deciding has still answered it
        for now — otherwise it would come back on the next page load."""
        onboarding.answer(
            "/api/me/data-sharing",
            httpx.Response(
                200, json={"has_identity": False, "state": "no_identity", "offers": []}
            ),
        )
        dismissed()

        body = client.get("/api/data-sharing", headers=auth_headers).json()

        assert body["asked"] is True
        assert body["review_due"] is False

    def test_a_stale_decision_brings_the_banner_back(
        self, client: TestClient, auth_headers: dict, enabled, onboarding, monkeypatch
    ):
        monkeypatch.setattr(settings, "data_sharing_review_after_days", 180)
        old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
        onboarding.answer(
            "/api/me/data-sharing",
            httpx.Response(
                200,
                json={
                    "has_identity": True,
                    "state": "ok",
                    "offers": [{"id": "a", "granted": True, "decided_at": old}],
                },
            ),
        )

        body = client.get("/api/data-sharing", headers=auth_headers).json()

        assert body["asked"] is True
        assert body["review_due"] is True

    def test_a_recent_dismissal_holds_a_stale_decision_off(
        self, client: TestClient, auth_headers: dict, enabled, onboarding, dismissed, monkeypatch
    ):
        """The member was reminded and closed it. Asking again tomorrow is
        nagging, and nagging is how a consent screen gets clicked through."""
        monkeypatch.setattr(settings, "data_sharing_review_after_days", 180)
        old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
        onboarding.answer(
            "/api/me/data-sharing",
            httpx.Response(
                200,
                json={
                    "has_identity": True,
                    "state": "ok",
                    "offers": [{"id": "a", "granted": True, "decided_at": old}],
                },
            ),
        )
        dismissed(days_ago=1)

        body = client.get("/api/data-sharing", headers=auth_headers).json()

        assert body["review_due"] is False


class TestPromptState:
    """The comparison itself, without a database or an app."""

    NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)

    def _offers(self, decided_at):
        return [{"id": "a", "decided_at": decided_at}]

    def test_never_asked(self):
        state = service.prompt_state(
            seen_at=None, offers=self._offers(None), after_days=180, now=self.NOW
        )

        assert state == service.Prompt(asked=False, review_due=False)

    def test_never_asked_is_never_review_due(self):
        """The two are different sentences. A first-timer must not be told to
        review a decision they have not made."""
        state = service.prompt_state(
            seen_at=None, offers=[], after_days=1, now=self.NOW
        )

        assert state.review_due is False

    def test_the_newest_stamp_wins(self):
        """A decision made after a dismissal restarts the clock, and so does a
        dismissal after a decision."""
        state = service.prompt_state(
            seen_at=self.NOW - timedelta(days=400),
            offers=self._offers((self.NOW - timedelta(days=2)).isoformat()),
            after_days=180,
            now=self.NOW,
        )

        assert state.review_due is False

    def test_zero_days_switches_the_reminder_off(self):
        """Ask once and never again, as a configuration rather than a code path."""
        state = service.prompt_state(
            seen_at=self.NOW - timedelta(days=4000),
            offers=self._offers(None),
            after_days=0,
            now=self.NOW,
        )

        assert state == service.Prompt(asked=True, review_due=False)

    def test_an_unreadable_stamp_does_not_crash_the_page(self):
        """Upstream's format is not this service's to police. Being wrong here
        costs one extra prompt; raising costs the whole page."""
        state = service.prompt_state(
            seen_at=None,
            offers=self._offers("last tuesday"),
            after_days=180,
            now=self.NOW,
        )

        assert state == service.Prompt(asked=False, review_due=False)

    def test_a_naive_timestamp_is_read_as_utc(self):
        """SQLite hands back naive datetimes and PostgreSQL does not, so the
        comparison must survive both. A naive stamp raises rather than
        misreporting if this is ever dropped."""
        state = service.prompt_state(
            seen_at=datetime(2025, 1, 1, 12, 0),
            offers=self._offers(None),
            after_days=180,
            now=self.NOW,
        )

        assert state == service.Prompt(asked=True, review_due=True)
