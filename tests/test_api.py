"""Test user API endpoints."""
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


def test_notifications_list(client: TestClient, auth_headers: dict):
    """Test listing notifications."""
    response = client.get("/api/notifications", headers=auth_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
