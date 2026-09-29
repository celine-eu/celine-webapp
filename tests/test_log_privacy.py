"""No application log links a member to their meter (celine-eu/celine-webapp#27).

Logs are shipped to and kept by the log backend. So at every level, including
DEBUG, no record may carry the member's sensor id or their user id. That holds on
failure too: a failed Digital Twin call raises an `httpx` error whose message is
the request URL, and the URL carries the participant id. The fakes below raise
exactly that shape, and the log still has to say only the error type and status.
"""

from __future__ import annotations

import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from celine.webapp.services.log_safety import failure

SUB = "test-user-123"
SENSOR = "c2g-57CFA0F18"


def _dt_error(fetcher: str) -> httpx.HTTPStatusError:
    """What the SDK raises for a refused fetch: the URL, with the participant in it."""
    url = f"http://dt.test/participants/{SUB}/values/{fetcher}?device_id={SENSOR}"
    request = httpx.Request("POST", url)
    response = httpx.Response(500, request=request)
    return httpx.HTTPStatusError(
        f"Server error '500 Internal Server Error' for url '{url}'",
        request=request,
        response=response,
    )


def _leaks(caplog: pytest.LogCaptureFixture) -> list[str]:
    """This repository's records that carry either identifier.

    Only `celine.*` loggers: at DEBUG the test database driver (`aiosqlite`) logs
    every statement with its bound parameters, the user id among them. That is a
    library's DEBUG output against the test database, not an application log.
    """
    return [
        f"{r.levelname} {r.name}: {r.getMessage()}"
        for r in caplog.records
        if r.name.startswith("celine.")
        and (SUB in r.getMessage() or SENSOR in r.getMessage())
    ]


@pytest.fixture
def debug_logs(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.DEBUG)
    return caplog


def test_the_gamification_route_logs_no_identifier(
    client: TestClient, auth_headers: dict, fake_dt, debug_logs
) -> None:
    fake_dt.participants.values["rec_participant_points"] = [
        {"ts_date": "2026-08-01", "daily_points": 10}
    ]

    assert client.get("/api/gamification", headers=auth_headers).status_code == 200

    assert _leaks(debug_logs) == []


@pytest.mark.parametrize("fetcher", ["rec_points_leaderboard", "rec_participant_points"])
def test_a_failed_points_fetch_logs_no_identifier(
    client: TestClient, auth_headers: dict, fake_dt, debug_logs, fetcher
) -> None:
    fake_dt.participants.value_errors[fetcher] = _dt_error(fetcher)

    assert client.get("/api/gamification", headers=auth_headers).status_code == 200

    assert _leaks(debug_logs) == []
    assert any("HTTPStatusError 500" in r.getMessage() for r in debug_logs.records)


@pytest.mark.parametrize("route", ["/api/gamification", "/api/overview"])
def test_a_failed_asset_lookup_logs_no_identifier(
    client: TestClient, auth_headers: dict, fake_dt, debug_logs, route
) -> None:
    fake_dt.participants.assets_error = _dt_error("assets")

    client.get(route, headers=auth_headers)

    assert _leaks(debug_logs) == []


@pytest.mark.parametrize(
    "fetcher", ["meters_data", "rec_virtual_consumption_per_device_15m"]
)
def test_a_failed_meter_fetch_on_the_overview_logs_no_identifier(
    client: TestClient, auth_headers: dict, fake_dt, debug_logs, fetcher
) -> None:
    fake_dt.participants.value_errors[fetcher] = _dt_error(fetcher)

    assert client.get("/api/overview", headers=auth_headers).status_code == 200

    assert _leaks(debug_logs) == []


def test_failure_names_the_type_and_status_and_nothing_else() -> None:
    assert failure(_dt_error("meters_data")) == "HTTPStatusError 500"
    assert failure(RuntimeError(f"boom for {SUB}")) == "RuntimeError"
