"""`GET /api/overview` — the fan-out this repository exists to perform.

The overview is the clearest example of what a backend-for-frontend actually owns. Its
own logic is not the energy figures, which the Digital Twin computes; it is the
*composition*: resolving the caller's community and device, issuing four separate value
fetches, summing them into two totals blocks, and folding the rest into a daily trend the
chart can render without further work.

Every one of those steps was previously untested. `test_overview_endpoint` asserted that
four keys were present and that the trend had seven entries — true of an all-nulls
response, which is exactly what the endpoint returns when every upstream call fails.

The tests here therefore assert the arithmetic and the degradation separately, because a
BFF is judged on both: what it composes when the upstreams answer, and what it still
serves when they do not.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from celine.sdk.dt.util import DTApiError
from celine.sdk.openapi.dt import errors as dt_errors

from tests.fakes import (
    FakeAsset,
    FakeAssets,
    FakeMember,
    FakeMembership,
    FakeParticipantProfile,
)


DEVICE = "c2g-57CFA0F18"


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).date().isoformat()


def _meter_rows() -> list[dict]:
    """Two readings a day for three days, so daily grouping has something to group."""
    rows = []
    for day_offset in (2, 1, 0):
        day = _days_ago(day_offset)
        rows.append({"ts": f"{day}T06:00:00", "consumption_kwh": 1.0, "production_kwh": 0.5})
        rows.append({"ts": f"{day}T18:00:00", "consumption_kwh": 3.0, "production_kwh": 1.5})
    return rows


def _rec_rows() -> list[dict]:
    rows = []
    for day_offset in (2, 1, 0):
        day = _days_ago(day_offset)
        rows.append(
            {
                "ts": f"{day}T06:00:00",
                "total_consumption_kwh": 100.0,
                "total_production_kwh": 40.0,
                "self_consumption_kwh": 25.0,
            }
        )
    return rows


# ─── Composition ─────────────────────────────────────────────────────────────


def test_user_totals_are_summed_across_every_reading(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    fake_dt.participants.values["meters_data"] = _meter_rows()

    body = client.get("/api/overview", headers=auth_headers).json()

    # 6 readings: consumption 3 x (1.0 + 3.0), production 3 x (0.5 + 1.5)
    assert body["user"]["consumption_kwh"] == pytest.approx(12.0)
    assert body["user"]["production_kwh"] == pytest.approx(6.0)


def test_shared_energy_comes_from_the_virtual_consumption_fetcher(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    """Self-consumption is a *separate* fetch, and the rate is derived from both."""
    fake_dt.participants.values["meters_data"] = _meter_rows()
    fake_dt.participants.values["rec_virtual_consumption_per_device_15m"] = [
        {"ts": f"{_days_ago(1)}T06:00:00", "virtual_consumption_kwh": 2.0},
        {"ts": f"{_days_ago(0)}T06:00:00", "virtual_consumption_kwh": 1.0},
    ]

    body = client.get("/api/overview", headers=auth_headers).json()

    assert body["user"]["self_consumption_kwh"] == pytest.approx(3.0)
    # 3.0 shared against 12.0 consumed
    assert body["user"]["self_consumption_rate"] == pytest.approx(0.25)


def test_community_totals_and_rate(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    fake_dt.communities.values["rec_self_consumption"] = _rec_rows()

    body = client.get("/api/overview", headers=auth_headers).json()

    assert body["rec"]["consumption_kwh"] == pytest.approx(300.0)
    assert body["rec"]["production_kwh"] == pytest.approx(120.0)
    assert body["rec"]["self_consumption_kwh"] == pytest.approx(75.0)
    assert body["rec"]["self_consumption_rate"] == pytest.approx(0.25)


def test_the_trend_groups_hourly_rows_into_days(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    """Three days of data inside a seven-day window: three filled, four empty."""
    fake_dt.communities.values["rec_self_consumption"] = _rec_rows()

    body = client.get("/api/overview", headers=auth_headers).json()
    trend = body["trend"]

    assert len(trend) == 7
    filled = [d for d in trend if d["consumption_kwh"] is not None]
    assert len(filled) == 3
    assert all(d["consumption_kwh"] == pytest.approx(100.0) for d in filled)
    # Surplus is derived, not fetched: production 40 against consumption 100 means none.
    assert all(d["surplus_kwh"] == pytest.approx(0.0) for d in filled)
    assert [d["date"] for d in trend] == sorted(d["date"] for d in trend)


def test_surplus_appears_when_production_exceeds_consumption(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    day = _days_ago(0)
    fake_dt.communities.values["rec_self_consumption"] = [
        {
            "ts": f"{day}T06:00:00",
            "total_consumption_kwh": 10.0,
            "total_production_kwh": 40.0,
            "self_consumption_kwh": 8.0,
        }
    ]

    trend = client.get("/api/overview", headers=auth_headers).json()["trend"]
    today = [d for d in trend if d["date"] == day][0]

    assert today["surplus_kwh"] == pytest.approx(30.0)


def test_devices_are_surfaced_from_participant_assets(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    fake_dt.participants.assets_result = FakeAssets(
        [
            FakeAsset(sensor_id=DEVICE, key="asset-1", name="Home meter", device={"model": "X"}),
            FakeAsset(sensor_id=None, key="asset-2", name="No sensor"),
        ]
    )

    body = client.get("/api/overview", headers=auth_headers).json()

    # The asset without a sensor id is dropped: it cannot be queried for values.
    assert [d["key"] for d in body["devices"]] == ["asset-1"]
    assert body["devices"][0]["details"] == {"model": "X"}


# ─── What gets asked of the Digital Twin ─────────────────────────────────────


def test_the_first_sensor_is_the_one_queried(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    fake_dt.participants.assets_result = FakeAssets(
        [FakeAsset(sensor_id=DEVICE), FakeAsset(sensor_id="second-device", key="asset-2")]
    )

    client.get("/api/overview", headers=auth_headers)

    meter_calls = [
        c for c in fake_dt.participants.calls if c.get("fetcher_id") == "meters_data"
    ]
    assert meter_calls[0]["payload"]["device_id"] == DEVICE


def test_the_device_is_always_the_first_asset_sensor(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    """There is no delivery-point path. The asset sensor is the only source of a device id.

    Guards the removal of a block that appeared to give `delivery_points[0].meter_id`
    precedence. See `test_the_membership_member_carries_no_delivery_points` below for why
    that block never ran.
    """
    fake_dt.participants.assets_result = FakeAssets([FakeAsset(sensor_id=DEVICE)])

    client.get("/api/overview", headers=auth_headers)

    fetches = [c for c in fake_dt.participants.calls if "fetcher_id" in c]
    assert fetches
    assert all(c["payload"]["device_id"] == DEVICE for c in fetches)


def test_the_community_queried_is_the_one_the_caller_belongs_to(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    fake_dt.participants.profile_result = FakeParticipantProfile(
        FakeMembership(community_key="community-42")
    )

    client.get("/api/overview", headers=auth_headers)

    assert fake_dt.communities.calls[0]["community_id"] == "community-42"


@pytest.mark.parametrize(
    ("days", "expected_fetcher"),
    [
        (7, "rec_self_consumption"),
        (30, "rec_self_consumption"),
        (31, "rec_self_consumption_daily"),
        (365, "rec_self_consumption_daily"),
    ],
)
def test_long_ranges_switch_to_the_daily_fetcher(
    client: TestClient, auth_headers: dict, fake_dt, days: int, expected_fetcher: str
) -> None:
    """Above thirty days the hourly fetcher is too much data to aggregate here.

    The threshold is unit-tested on `_rec_self_consumption_fetcher_id`; this pins that
    the endpoint actually routes on it, which the unit test cannot see.
    """
    client.get(f"/api/overview?days={days}", headers=auth_headers)

    assert fake_dt.communities.calls[0]["fetcher_id"] == expected_fetcher


def test_a_custom_range_is_forwarded_as_an_inclusive_window(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    """The query end is exclusive midnight, so the last day is included in full."""
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=4)

    body = client.get(
        f"/api/overview?start_date={start.isoformat()}&end_date={end.isoformat()}",
        headers=auth_headers,
    ).json()

    payload = fake_dt.communities.calls[0]["payload"]
    assert payload["start"].startswith(start.isoformat())
    assert payload["end"].startswith((end + timedelta(days=1)).isoformat())
    assert body["period"] == f"{start.isoformat()} to {end.isoformat()}"
    assert len(body["trend"]) == 5


# ─── Degradation: four upstreams, any of which can be down ───────────────────


def test_a_participant_the_twin_does_not_know_is_a_404(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    fake_dt.participants.profile_error = DTApiError("nope", status_code=404)

    response = client.get("/api/overview", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "not_a_participant"


def test_the_generated_client_404_is_treated_the_same_way(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    """Two SDK layers raise two different exceptions for one condition.

    `DTApiError` comes from the hand-written client, `UnexpectedStatus` from the
    generated one. The route handles both, and it must keep doing so.
    """
    fake_dt.participants.profile_error = dt_errors.UnexpectedStatus(404, b"not found")

    response = client.get("/api/overview", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "not_a_participant"


def test_a_twin_failure_that_is_not_a_404_is_not_swallowed(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    """A broken twin must not be reported to the app as an empty overview.

    Only 404 is translated; anything else propagates, which FastAPI serves as a 500. The
    test asserts the propagation directly because `TestClient` re-raises server
    exceptions rather than rendering them — see `raise_server_exceptions`.
    """
    fake_dt.participants.profile_error = DTApiError("boom", status_code=500)

    with pytest.raises(DTApiError):
        client.get("/api/overview", headers=auth_headers)


@pytest.mark.parametrize(
    "membership",
    [
        pytest.param(None, id="no-membership"),
        pytest.param(FakeMembership(member=None), id="membership-without-member"),
    ],
)
def test_a_participant_without_a_membership_is_a_404(
    client: TestClient, auth_headers: dict, fake_dt, membership
) -> None:
    """Known to the twin but not placed in a community — a real state, not an error path.

    Both halves are checked: the membership itself may be absent, or present with no
    member record behind it. The route rejects each, and the app treats the two the same.
    """
    fake_dt.participants.profile_result = FakeParticipantProfile(membership=membership)

    assert client.get("/api/overview", headers=auth_headers).status_code == 404


def test_failing_value_fetches_degrade_to_nulls_rather_than_an_error(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    """The dashboard renders with gaps rather than not rendering.

    This is a deliberate trade in the route and worth pinning: a member whose meter data
    is briefly unavailable still sees the page, and the community column still fills.
    """
    fake_dt.participants.value_errors["meters_data"] = RuntimeError("twin down")
    fake_dt.communities.values["rec_self_consumption"] = _rec_rows()

    response = client.get("/api/overview", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["consumption_kwh"] is None
    assert body["rec"]["consumption_kwh"] == pytest.approx(300.0)


def test_an_empty_upstream_still_yields_a_full_length_trend(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    """The chart always gets one entry per day, filled or not."""
    body = client.get("/api/overview?days=14", headers=auth_headers).json()

    assert len(body["trend"]) == 14
    assert all(d["consumption_kwh"] is None for d in body["trend"])


def test_a_participant_with_no_assets_still_gets_community_figures(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    """No meter is a normal state — a member can join before their device is registered."""
    fake_dt.participants.assets_result = FakeAssets([])
    fake_dt.communities.values["rec_self_consumption"] = _rec_rows()

    body = client.get("/api/overview", headers=auth_headers).json()

    assert body["user"]["consumption_kwh"] is None
    assert body["rec"]["consumption_kwh"] == pytest.approx(300.0)
    assert body["devices"] == []
    # No device means no meter fetch was attempted at all.
    assert not [
        c for c in fake_dt.participants.calls if c.get("fetcher_id") == "meters_data"
    ]


# ─── Window validation ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "query",
    [
        "start_date=2026-01-01",
        "end_date=2026-01-01",
        "start_date=2026-02-01&end_date=2026-01-01",
    ],
)
def test_malformed_windows_are_rejected(
    client: TestClient, auth_headers: dict, query: str
) -> None:
    assert client.get(f"/api/overview?{query}", headers=auth_headers).status_code == 400


def test_a_future_end_date_is_rejected(client: TestClient, auth_headers: dict) -> None:
    future = date.today() + timedelta(days=2)
    response = client.get(
        f"/api/overview?start_date={date.today().isoformat()}&end_date={future.isoformat()}",
        headers=auth_headers,
    )
    assert response.status_code == 400
