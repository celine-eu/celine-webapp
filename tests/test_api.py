"""Test user API endpoints."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient


def test_me_endpoint_requires_auth(client: TestClient):
    """Test /api/me requires authentication."""
    response = client.get("/api/me")
    assert response.status_code == 401


def test_me_endpoint_with_auth(client: TestClient, auth_headers: dict):
    """Test /api/me with authentication."""
    response = client.get("/api/me", headers=auth_headers)
    assert response.status_code == 200
    
    data = response.json()
    assert "user" in data
    assert data["user"]["sub"] == "test-user-123"
    assert data["user"]["email"] == "test@example.com"
    assert data["has_smart_meter"] is False
    assert data["terms_required"] is True
    assert data["onboarding_seen"] is False
    assert data["onboarding_seen_pages"] == []


def test_mark_onboarding_seen(client: TestClient, auth_headers: dict):
    """Test marking onboarding as seen."""
    response = client.post(
        "/api/onboarding/seen",
        headers=auth_headers,
        json={"page_key": "/notifications"},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True

    me_response = client.get("/api/me", headers=auth_headers)
    assert me_response.status_code == 200
    assert "/notifications" in me_response.json()["onboarding_seen_pages"]


def test_accept_terms(client: TestClient, auth_headers: dict):
    """Test accepting terms."""
    response = client.post(
        "/api/terms/accept",
        headers=auth_headers,
        json={"accept": True}
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    
    # Verify terms were accepted
    me_response = client.get("/api/me", headers=auth_headers)
    assert me_response.json()["terms_required"] is False


def test_get_settings(client: TestClient, auth_headers: dict):
    """Test getting user settings."""
    response = client.get("/api/settings", headers=auth_headers)
    assert response.status_code == 200
    
    data = response.json()
    assert "simple_mode" in data
    assert "font_scale" in data
    assert "notifications" in data
    assert data["notifications"]["limit"] == 5
    assert len(data["notifications"]["kinds"]) == 3
    assert data["notifications"]["kinds"][0]["kind"] == "meter_anomaly"
    assert data["notifications"]["kinds"][2]["kind"] == "extr_event"
    assert data["notifications"]["kinds"][2]["editable"] is False


def test_update_settings(client: TestClient, auth_headers: dict):
    """Test updating user settings."""
    new_settings = {
        "simple_mode": True,
        "font_scale": 1.2,
        "notifications": {
            "email_enabled": True,
            "email": "test@example.com",
            "webpush_enabled": True,
            "limit": 8,
            "kinds": [
                {
                    "kind": "meter_anomaly",
                    "label": "Sensor and meter anomalies",
                    "description": "Alerts for faulty devices.",
                    "cadence": "At most once per day.",
                    "enabled": True,
                },
                {
                    "kind": "price_up",
                    "label": "Price increase alerts",
                    "description": "Alerts when prices rise.",
                    "cadence": "At most once per day.",
                    "enabled": False,
                    "editable": True,
                },
                {
                    "kind": "extr_event",
                    "label": "Weather alerts",
                    "description": "Relevant weather alerts for the community.",
                    "cadence": "When a relevant alert is issued.",
                    "enabled": True,
                    "editable": False,
                },
            ],
        },
    }
    
    response = client.put(
        "/api/settings",
        headers=auth_headers,
        json=new_settings
    )
    assert response.status_code == 200
    
    data = response.json()
    assert data["simple_mode"] is True
    assert data["font_scale"] == 1.2
    assert data["notifications"]["email_enabled"] is True
    assert data["notifications"]["limit"] == 8
    assert data["notifications"]["webpush_enabled"] is True
    assert data["notifications"]["kinds"][1]["enabled"] is False
    assert data["notifications"]["kinds"][2]["enabled"] is True
    assert data["notifications"]["kinds"][2]["editable"] is False


def test_overview_endpoint(client: TestClient, auth_headers: dict):
    """Test overview endpoint."""
    response = client.get("/api/overview", headers=auth_headers)
    assert response.status_code == 200
    
    data = response.json()
    assert "period" in data
    assert "user" in data
    assert "rec" in data
    assert "trend" in data
    assert len(data["trend"]) == 7


def test_overview_window_accepts_custom_range():
    """Test custom overview date windows are inclusive for charts."""
    from celine.webapp.api.overview import _resolve_overview_window

    end = datetime.now(timezone.utc).date() - timedelta(days=1)
    start = end - timedelta(days=9)

    query_start, query_end, trend_end, range_days, period = _resolve_overview_window(
        days=7,
        start_date=start,
        end_date=end,
    )

    assert query_start.date() == start
    assert query_end.date() == end + timedelta(days=1)
    assert trend_end.date() == end
    assert range_days == 10
    assert period == f"{start.isoformat()} to {end.isoformat()}"


def test_overview_window_rejects_ranges_longer_than_one_year():
    """Test custom overview ranges are capped at one year."""
    from fastapi import HTTPException
    from celine.webapp.api.overview import _resolve_overview_window

    end = datetime.now(timezone.utc).date() - timedelta(days=1)
    start = end - timedelta(days=366)

    with pytest.raises(HTTPException) as exc:
        _resolve_overview_window(days=7, start_date=start, end_date=end)

    assert exc.value.status_code == 400


def test_overview_uses_daily_rec_fetcher_only_for_large_ranges():
    """Test REC self-consumption fetcher selection keeps short ranges unchanged."""
    from celine.webapp.api.overview import _rec_self_consumption_fetcher_id

    assert _rec_self_consumption_fetcher_id(30) == "rec_self_consumption"
    assert _rec_self_consumption_fetcher_id(31) == "rec_self_consumption_daily"


def test_notifications_list(client: TestClient, auth_headers: dict):
    """Test listing notifications."""
    response = client.get("/api/notifications", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_suggestion_item_allows_missing_personal_fields() -> None:
    """Test that SuggestionItem validates without impact_kwh_estimated/reward_points."""
    from celine.webapp.api.schemas import SuggestionItem

    item = SuggestionItem(
        id="w1", suggestion_type="shift-consumption",
        period_start="2026-07-02T09:00:00", period_end="2026-07-02T12:00:00",
        from_period="", clock_range="09:00–12:00", to_is_tomorrow=False,
        to_period="morning", to_time="09:00", community_kwh=120.0,
    )
    assert item.impact_kwh_estimated is None
    assert item.reward_points is None
