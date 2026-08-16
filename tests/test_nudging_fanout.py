"""Settings and notifications — the fan-out to `../nudging-tool`.

Settings are split across two owners and the split is invisible to the app. `simple_mode`,
`font_scale` and `webpush_enabled` are this repository's own rows; the notification limit,
the email channel and the per-kind catalogue belong to the nudging tool. `GET /api/settings`
merges them into one object and `PUT` takes one object apart again.

That merge is where the interesting failures live: a preference written to the wrong side
is lost silently, and a catalogue that fails to load degrades differently from preferences
that fail to load. Both behaviours are deliberate and neither was covered.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.fakes import FakeNotification


def _settings_payload(**overrides) -> dict:
    payload = {
        "simple_mode": True,
        "font_scale": 1.2,
        "notifications": {
            "email_enabled": True,
            "email": "member@example.com",
            "webpush_enabled": True,
            "limit": 8,
            "kinds": [
                {"kind": "meter_anomaly", "label": "A", "description": "", "cadence": "", "enabled": True},
                {"kind": "price_up", "label": "B", "description": "", "cadence": "", "enabled": False},
                {"kind": "extr_event", "label": "C", "description": "", "cadence": "", "enabled": True, "editable": False},
            ],
        },
    }
    payload.update(overrides)
    return payload


# ─── The merge ───────────────────────────────────────────────────────────────


def test_settings_merge_local_rows_with_upstream_preferences(
    client: TestClient, auth_headers: dict, fake_nudging
) -> None:
    fake_nudging.max_per_day = 7
    fake_nudging.channel_email = True
    fake_nudging.email = "member@example.com"

    body = client.get("/api/settings", headers=auth_headers).json()

    # From the nudging tool
    assert body["notifications"]["limit"] == 7
    assert body["notifications"]["email_enabled"] is True
    assert body["notifications"]["email"] == "member@example.com"
    # From this repository's own database
    assert body["simple_mode"] is False
    assert body["font_scale"] == 1.0


def test_a_round_trip_preserves_every_field(
    client: TestClient, auth_headers: dict
) -> None:
    """PUT then GET. The split between the two owners must be invisible to the app."""
    assert client.put(
        "/api/settings", headers=auth_headers, json=_settings_payload()
    ).status_code == 200

    body = client.get("/api/settings", headers=auth_headers).json()

    assert body["simple_mode"] is True
    assert body["font_scale"] == 1.2
    assert body["notifications"]["limit"] == 8
    assert body["notifications"]["email_enabled"] is True
    assert body["notifications"]["webpush_enabled"] is True


def test_only_the_enabled_kinds_are_sent_upstream(
    client: TestClient, auth_headers: dict, fake_nudging
) -> None:
    client.put("/api/settings", headers=auth_headers, json=_settings_payload())

    assert fake_nudging.updates
    assert fake_nudging.updates[-1]["enabled_notification_kinds"] == [
        "meter_anomaly",
        "extr_event",
    ]


def test_a_disabled_kind_comes_back_disabled(
    client: TestClient, auth_headers: dict
) -> None:
    body = client.put(
        "/api/settings", headers=auth_headers, json=_settings_payload()
    ).json()

    kinds = {k["kind"]: k for k in body["notifications"]["kinds"]}
    assert kinds["price_up"]["enabled"] is False
    assert kinds["meter_anomaly"]["enabled"] is True


def test_a_non_editable_kind_stays_non_editable(
    client: TestClient, auth_headers: dict
) -> None:
    """`extr_event` is not a member's to switch off, and the flag must survive the round trip."""
    body = client.put(
        "/api/settings", headers=auth_headers, json=_settings_payload()
    ).json()

    kinds = {k["kind"]: k for k in body["notifications"]["kinds"]}
    assert kinds["extr_event"]["editable"] is False


# ─── Language, which the catalogue is rendered in ────────────────────────────


def test_the_language_query_parameter_reaches_the_nudging_tool(
    client: TestClient, auth_headers: dict, fake_nudging
) -> None:
    client.put("/api/settings?lang=it", headers=auth_headers, json=_settings_payload())

    assert fake_nudging.updates[-1]["lang"] == "it"


def test_accept_language_is_used_when_no_parameter_is_given(
    client: TestClient, auth_headers: dict, fake_nudging
) -> None:
    client.put(
        "/api/settings",
        headers={**auth_headers, "accept-language": "es-ES,es;q=0.9,en;q=0.8"},
        json=_settings_payload(),
    )

    assert fake_nudging.updates[-1]["lang"] == "es"


def test_an_unsupported_language_is_dropped_rather_than_forwarded(
    client: TestClient, auth_headers: dict, fake_nudging
) -> None:
    """Only it/en/es are supported. Anything else must not reach the upstream as-is."""
    client.put(
        "/api/settings",
        headers={**auth_headers, "accept-language": "de-DE"},
        json=_settings_payload(),
    )

    assert fake_nudging.updates[-1]["lang"] is None


# ─── Validation and degradation ──────────────────────────────────────────────


@pytest.mark.parametrize("email", ["", "   ", "not-an-email", "missing@domain"])
def test_enabling_email_without_a_valid_address_is_rejected(
    lenient_client: TestClient, auth_headers: dict, fake_nudging, email: str
) -> None:
    """Answered 500 until 2026-08-15 — a mistyped address rendered as an outage.

    `update_settings` reads the body itself, so FastAPI's dependency layer never validates
    it and the raw pydantic `ValidationError` escaped the handler unhandled.
    """
    payload = _settings_payload()
    payload["notifications"]["email"] = email

    response = lenient_client.put("/api/settings", headers=auth_headers, json=payload)

    assert response.status_code == 422
    # Nothing was sent upstream: the request never got that far.
    assert not fake_nudging.updates


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        ("", "Email address is required when email notifications are enabled"),
        ("not-an-email", "Email address format is invalid"),
    ],
)
def test_the_rejection_message_is_a_plain_string_the_app_can_display(
    lenient_client: TestClient, auth_headers: dict, email: str, expected: str
) -> None:
    """`detail` is a string, not FastAPI's array of error objects.

    The route's 422 contract predates this fix and the app renders `detail` directly, so
    the shape matters as much as the status. Pydantic's "Value error, " prefix is stripped.
    """
    payload = _settings_payload()
    payload["notifications"]["email"] = email

    body = lenient_client.put("/api/settings", headers=auth_headers, json=payload).json()

    assert body["detail"] == expected


def test_a_malformed_body_is_a_422_rather_than_a_500(
    lenient_client: TestClient, auth_headers: dict
) -> None:
    """Not only the email path: any unvalidatable body must be a 422.

    `font_scale` is bounded 0.9–1.3 in the model, and that bound is enforced by the same
    `model_validate` call, so it took the same route to a 500.
    """
    payload = _settings_payload()
    payload["font_scale"] = 99.0

    response = lenient_client.put("/api/settings", headers=auth_headers, json=payload)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_an_invalid_email_never_reaches_the_nudging_tool(
    lenient_client: TestClient, auth_headers: dict, fake_nudging
) -> None:
    """The status is wrong (see above) but the rejection itself holds.

    This is the half worth guarding regardless of which code is returned: a bad address
    must not be written upstream, because the nudging tool would then send to it.
    """
    payload = _settings_payload()
    payload["notifications"]["email"] = "not-an-email"

    lenient_client.put("/api/settings", headers=auth_headers, json=payload)

    assert not fake_nudging.updates


def test_an_out_of_range_limit_from_upstream_is_clamped_to_a_default(
    client: TestClient, auth_headers: dict, fake_nudging
) -> None:
    """A limit outside 1..10 is not trusted; the route substitutes 3 rather than showing it."""
    fake_nudging.max_per_day = 99

    body = client.get("/api/settings", headers=auth_headers).json()

    assert body["notifications"]["limit"] == 3


def test_unreachable_preferences_are_a_502(
    client: TestClient, auth_headers: dict, fake_nudging, monkeypatch
) -> None:
    """Settings cannot be rendered half-known, so this one fails loudly."""

    async def boom(*args, **kwargs):
        raise RuntimeError("nudging down")

    monkeypatch.setattr(fake_nudging, "get_preferences", boom)

    assert client.get("/api/settings", headers=auth_headers).status_code == 502


def test_an_unreachable_catalogue_degrades_quietly_instead(
    client: TestClient, auth_headers: dict, fake_nudging, monkeypatch
) -> None:
    """The catalogue is decoration around the preferences, so its loss is survivable.

    The asymmetry with the test above is deliberate in the route: preferences missing
    means the page would lie, an empty catalogue means it shows fewer switches.
    """

    async def boom(*args, **kwargs):
        raise RuntimeError("nudging down")

    monkeypatch.setattr(fake_nudging, "get_preference_catalog", boom)

    response = client.get("/api/settings", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["notifications"]["kinds"] == []


def test_a_failed_upstream_update_is_a_502(
    client: TestClient, auth_headers: dict, fake_nudging, monkeypatch
) -> None:
    async def boom(*args, **kwargs):
        raise RuntimeError("nudging down")

    monkeypatch.setattr(fake_nudging, "update_preferences", boom)

    assert client.put(
        "/api/settings", headers=auth_headers, json=_settings_payload()
    ).status_code == 502


# ─── Notifications ───────────────────────────────────────────────────────────


def test_notifications_are_mapped_from_the_nudging_tool(
    client: TestClient, auth_headers: dict, fake_nudging
) -> None:
    from datetime import datetime, timezone

    fake_nudging.notifications = [
        FakeNotification(
            id="n-1",
            title="Meter anomaly",
            severity="critical",
            read_at=datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc),
        )
    ]

    body = client.get("/api/notifications", headers=auth_headers).json()

    assert len(body) == 1
    assert body[0]["id"] == "n-1"
    assert body[0]["severity"] == "critical"
    assert body[0]["read_at"] == "2026-08-02T10:00:00+00:00"
    assert body[0]["deleted_at"] is None


@pytest.mark.parametrize(
    ("upstream", "expected"),
    [
        ("critical", "critical"),
        ("warning", "warning"),
        ("info", "info"),
        ("something-new", "info"),
    ],
)
def test_unknown_severities_collapse_to_info(
    client: TestClient, auth_headers: dict, fake_nudging, upstream: str, expected: str
) -> None:
    """The app renders three severities. A fourth introduced upstream must not break it."""
    fake_nudging.notifications = [FakeNotification(severity=upstream)]

    body = client.get("/api/notifications", headers=auth_headers).json()

    assert body[0]["severity"] == expected


def test_no_notifications_is_an_empty_list_not_an_error(
    client: TestClient, auth_headers: dict
) -> None:
    response = client.get("/api/notifications", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == []
