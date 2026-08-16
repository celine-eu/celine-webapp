"""`GET /api/gamification` — season scoring, and the fallback when it is unavailable.

The endpoint composes three sources: badges and accepted-suggestion counts from this
repository's own database, season standing from the Digital Twin's
`rec_points_leaderboard`, and daily points from `rec_participant_points`.

The mapping functions are already unit-tested in `test_api.py`. What was untested is the
route's *selection* between the two modes, which is the part that decides what a member
actually sees:

- when the leaderboard row is usable, it supplies the headline total and the ranking, and
  the daily points that were summed are discarded in favour of it;
- when it is not — an older twin deployment, a device not yet in the fleet, a malformed
  row — the endpoint falls back to the all-time sum and shows no ranking at all.

That fallback is the interesting half, because it is silent. Nothing in the response says
"this is degraded"; the ranking is simply absent.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.fakes import FakeAsset, FakeAssets


def _leaderboard_row(**overrides) -> dict:
    row = {
        "device_id": "c2g-57CFA0F18",
        "season_start": "2026-07-01",
        "season_end": "2026-09-01",
        "season_base_points": 120,
        "season_bonus_points": 30,
        "season_points": 150,
        "season_rank": 3,
        "total_members": 14,
    }
    row.update(overrides)
    return row


def _points_rows() -> list[dict]:
    return [
        {"ts_date": "2026-08-03", "daily_points": 10},
        {"ts_date": "2026-08-01", "daily_points": 25},
        {"ts_date": "2026-08-02", "daily_points": 5},
    ]


# ─── Season mode ─────────────────────────────────────────────────────────────


def test_the_season_row_supplies_the_headline_and_the_ranking(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    fake_dt.participants.values["rec_points_leaderboard"] = [_leaderboard_row()]
    fake_dt.participants.values["rec_participant_points"] = _points_rows()

    body = client.get("/api/gamification", headers=auth_headers).json()

    assert body["total_points"] == 150
    assert body["season_base_points"] == 120
    assert body["season_bonus_points"] == 30
    assert body["season_start"] == "2026-07-01"
    assert body["ranking"]["position"] == 3
    assert body["ranking"]["period"] == "season"


def test_the_season_total_overrides_the_summed_daily_points(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    """The daily rows still sum to 40, and the season total wins anyway.

    Worth pinning explicitly: both numbers are computed, and picking the wrong one is a
    one-line mistake that no schema would catch.
    """
    fake_dt.participants.values["rec_points_leaderboard"] = [_leaderboard_row()]
    fake_dt.participants.values["rec_participant_points"] = _points_rows()

    body = client.get("/api/gamification", headers=auth_headers).json()

    assert sum(p["points"] for p in body["daily_points"]) == 40
    assert body["total_points"] == 150


def test_the_level_ladder_is_scoped_to_season_points(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    """100 points per level, applied to the season total, so the ladder resets each season."""
    fake_dt.participants.values["rec_points_leaderboard"] = [
        _leaderboard_row(season_points=250)
    ]

    body = client.get("/api/gamification", headers=auth_headers).json()

    assert body["total_points"] == 250
    assert body["level"] == 3
    assert body["next_level_at"] == 300


def test_daily_points_are_returned_in_date_order(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    """The twin does not promise an order; the chart needs one."""
    fake_dt.participants.values["rec_participant_points"] = _points_rows()

    body = client.get("/api/gamification", headers=auth_headers).json()

    assert [p["date"] for p in body["daily_points"]] == [
        "2026-08-01",
        "2026-08-02",
        "2026-08-03",
    ]


# ─── Fallback mode ───────────────────────────────────────────────────────────


def test_without_a_leaderboard_row_the_all_time_sum_is_used_and_no_rank_shown(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    fake_dt.participants.values["rec_participant_points"] = _points_rows()

    body = client.get("/api/gamification", headers=auth_headers).json()

    assert body["total_points"] == 40
    assert body["ranking"] is None
    assert body["season_start"] is None
    assert body["season_base_points"] is None


def test_a_leaderboard_fetch_failure_falls_back_rather_than_failing(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    """An older twin deployment does not know this fetcher. The panel still renders."""
    fake_dt.participants.value_errors["rec_points_leaderboard"] = RuntimeError(
        "unknown fetcher"
    )
    fake_dt.participants.values["rec_participant_points"] = _points_rows()

    response = client.get("/api/gamification", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["total_points"] == 40
    assert response.json()["ranking"] is None


def test_a_malformed_leaderboard_row_falls_back(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    """A row that arrives but cannot be mapped is treated as no row at all."""
    fake_dt.participants.values["rec_points_leaderboard"] = [
        _leaderboard_row(season_rank=None)
    ]
    fake_dt.participants.values["rec_participant_points"] = _points_rows()

    body = client.get("/api/gamification", headers=auth_headers).json()

    assert body["total_points"] == 40
    assert body["ranking"] is None


def test_a_points_fetch_failure_still_returns_a_usable_response(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    fake_dt.participants.value_errors["rec_participant_points"] = RuntimeError("down")

    response = client.get("/api/gamification", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["total_points"] == 0
    assert response.json()["daily_points"] == []


# ─── Device resolution, which gates everything above ─────────────────────────


def test_no_device_means_no_points_are_fetched_at_all(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    """Both fetches are keyed by device id, so a member without one gets zeros.

    Not an error: a member can exist before their meter is registered.
    """
    fake_dt.participants.assets_result = FakeAssets([])

    body = client.get("/api/gamification", headers=auth_headers).json()

    assert body["total_points"] == 0
    assert body["level"] == 1
    assert not [c for c in fake_dt.participants.calls if "fetcher_id" in c]


def test_the_first_asset_carrying_a_sensor_is_the_device_used(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    fake_dt.participants.assets_result = FakeAssets(
        [
            FakeAsset(sensor_id=None, key="no-sensor"),
            FakeAsset(sensor_id="the-device", key="has-sensor"),
        ]
    )
    fake_dt.participants.values["rec_participant_points"] = _points_rows()

    client.get("/api/gamification", headers=auth_headers)

    fetches = [c for c in fake_dt.participants.calls if "fetcher_id" in c]
    assert fetches
    assert all(c["payload"]["device_id"] == "the-device" for c in fetches)


def test_an_asset_lookup_failure_degrades_to_zero_rather_than_erroring(
    client: TestClient, auth_headers: dict, fake_dt
) -> None:
    fake_dt.participants.assets_error = RuntimeError("twin down")

    response = client.get("/api/gamification", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["total_points"] == 0


# ─── The half that comes from this repository's own database ─────────────────


def test_badges_and_actions_start_empty_for_a_new_member(
    client: TestClient, auth_headers: dict
) -> None:
    body = client.get("/api/gamification", headers=auth_headers).json()

    assert body["badges"] == []
    assert body["actions_taken"] == 0
