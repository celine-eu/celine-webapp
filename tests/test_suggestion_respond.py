"""`POST /api/suggestions/{id}/respond` — flexibility-api's refusals reach the member.

flexibility-api refuses an accept it could never settle, with a fixed contract:

* 409 ``{"detail": {"code": "no_meter", ...}}`` — the participant has no meter;
* 409 ``{"detail": {"code": "not_a_member", ...}}`` — no community membership;
* 503 ``{"detail": {"code": "dt_unavailable", ...}}`` — the twin or registry is down.

The frontend words its message on ``detail.code``, so the status and the code must
cross this service unchanged — and a refused accept must not be recorded here as if it
had succeeded, which is what swallowing the error used to do.

Only the socket is replaced: the real ``FlexibilityClient`` and its generated client run,
so the error shape the SDK raises for these statuses is exercised, not assumed.
"""

from __future__ import annotations

import asyncio
import json
import uuid

import httpx
import pytest
from celine.sdk.flexibility import FlexibilityClient
from sqlalchemy import func, select

from celine.webapp.api.deps import get_flexibility_client
from celine.webapp.db.models import SuggestionInteraction, UserBadge

FLEX_URL = "http://flexibility.test"
SUGGESTION_ID = "window-2026-10-27T10"
ACCEPT = {
    "response": "accepted",
    "reward_points": 10,
    "period_start": "2026-10-27T10:00:00+00:00",
    "period_end": "2026-10-27T12:00:00+00:00",
}


@pytest.fixture
def flex_answer(app, mock_upstream_http):
    """Make flexibility-api answer the respond call with ``status`` and ``body``."""

    app.dependency_overrides[get_flexibility_client] = lambda: FlexibilityClient(
        base_url=FLEX_URL, default_token="member-jwt"
    )

    def _answer(status: int, body: object) -> list[httpx.Request]:
        return mock_upstream_http(lambda request: httpx.Response(status, json=body))

    return _answer


def _count(db_sessionmaker, model) -> int:
    async def _run() -> int:
        async with db_sessionmaker() as session:
            return (await session.execute(select(func.count()).select_from(model))).scalar() or 0

    return asyncio.run(_run())


@pytest.mark.parametrize(
    ("status", "code"),
    [(409, "no_meter"), (409, "not_a_member"), (503, "dt_unavailable")],
)
def test_a_refused_accept_reaches_the_member_with_its_status_and_code(
    lenient_client, auth_headers, flex_answer, status, code
) -> None:
    seen = flex_answer(status, {"detail": {"code": code, "message": "refused upstream"}})

    res = lenient_client.post(
        f"/api/suggestions/{SUGGESTION_ID}/respond", json=ACCEPT, headers=auth_headers
    )

    assert res.status_code == status
    assert res.json()["detail"] == {"code": code, "message": "refused upstream"}
    assert len(seen) == 1
    assert seen[0].url.path == f"/api/suggestions/{SUGGESTION_ID}/respond"


def test_a_refused_accept_is_not_recorded_and_earns_no_badge(
    lenient_client, auth_headers, flex_answer, db_sessionmaker
) -> None:
    flex_answer(409, {"detail": {"code": "no_meter", "message": "no meter"}})

    res = lenient_client.post(
        f"/api/suggestions/{SUGGESTION_ID}/respond", json=ACCEPT, headers=auth_headers
    )

    assert res.status_code == 409
    assert _count(db_sessionmaker, SuggestionInteraction) == 0
    assert _count(db_sessionmaker, UserBadge) == 0


def test_a_refusal_without_a_code_still_keeps_its_status(
    lenient_client, auth_headers, flex_answer
) -> None:
    """An older flexibility-api, or a proxy in front of it, answers a plain detail."""
    flex_answer(503, {"detail": "Service Unavailable"})

    res = lenient_client.post(
        f"/api/suggestions/{SUGGESTION_ID}/respond", json=ACCEPT, headers=auth_headers
    )

    assert res.status_code == 503
    assert res.json()["detail"]["code"] is None


def test_the_upstream_body_is_not_logged(
    lenient_client, auth_headers, flex_answer, caplog
) -> None:
    flex_answer(409, {"detail": {"code": "no_meter", "message": "participant test-user-123"}})

    with caplog.at_level("DEBUG", logger="celine"):
        lenient_client.post(
            f"/api/suggestions/{SUGGESTION_ID}/respond", json=ACCEPT, headers=auth_headers
        )

    assert "test-user-123" not in caplog.text


def test_an_accepted_window_still_answers_with_its_commitment(
    client, auth_headers, flex_answer, db_sessionmaker
) -> None:
    commitment_id = str(uuid.uuid4())
    flex_answer(
        200,
        {"status": "committed", "commitment_id": commitment_id, "reward_points_estimated": 10},
    )

    res = client.post(
        f"/api/suggestions/{SUGGESTION_ID}/respond", json=ACCEPT, headers=auth_headers
    )

    assert res.status_code == 200
    assert res.json()["pending_commitment"]["id"] == commitment_id
    assert _count(db_sessionmaker, SuggestionInteraction) == 1


def test_the_contract_body_is_what_the_sdk_hands_back() -> None:
    """The SDK documents only 200/422 for respond, so a 409 surfaces as `UnexpectedStatus`
    carrying the raw body. The route depends on exactly that; pin it."""
    from celine.sdk.openapi.flexibility.errors import UnexpectedStatus

    body = json.dumps({"detail": {"code": "no_meter", "message": "m"}}).encode()
    exc = UnexpectedStatus(409, body)
    assert exc.status_code == 409
    assert json.loads(exc.content)["detail"]["code"] == "no_meter"
