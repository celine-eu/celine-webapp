"""Test configuration and fixtures."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from celine.webapp.main import create_app
from celine.webapp.db import Base, get_db
from celine.webapp.api.deps import get_nudging_client


class FakeNudgingClient:
    def __init__(self):
        self.max_per_day = 5
        self.channel_email = False
        self.email = ""
        self.enabled_notification_kinds = ["meter_anomaly", "price_up"]
        self.catalog = [
            {
                "kind": "meter_anomaly",
                "label": "Sensor and meter anomalies",
                "description": "Alerts for faulty devices.",
                "cadence": "At most once per day.",
                "enabled": True,
                "editable": True,
            },
            {
                "kind": "price_up",
                "label": "Price increase alerts",
                "description": "Alerts when prices rise.",
                "cadence": "At most once per day.",
                "enabled": True,
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
        ]

    async def get_preferences(self, *, token=None):
        class Pref:
            def __init__(self, max_per_day: int, channel_email: bool, email: str, enabled_notification_kinds: list[str]):
                self.max_per_day = max_per_day
                self.channel_email = channel_email
                self.email = email
                self.enabled_notification_kinds = enabled_notification_kinds

        return Pref(
            self.max_per_day,
            self.channel_email,
            self.email,
            list(self.enabled_notification_kinds),
        )

    async def update_preferences(
        self,
        max_per_day: int,
        channel_email: bool | None = None,
        email: str | None = None,
        enabled_notification_kinds: list[str] | None = None,
        *,
        token=None,
    ):
        self.max_per_day = max_per_day
        if channel_email is not None:
            self.channel_email = channel_email
        if email is not None:
            self.email = email
        if enabled_notification_kinds is not None:
            self.enabled_notification_kinds = enabled_notification_kinds
            for item in self.catalog:
                item["enabled"] = item["kind"] in enabled_notification_kinds

        class Pref:
            def __init__(self, max_per_day: int, channel_email: bool, email: str, enabled_notification_kinds: list[str]):
                self.max_per_day = max_per_day
                self.channel_email = channel_email
                self.email = email
                self.enabled_notification_kinds = enabled_notification_kinds

        return Pref(
            self.max_per_day,
            self.channel_email,
            self.email,
            list(self.enabled_notification_kinds),
        )

    async def get_preference_catalog(self, *, lang=None, token=None):
        return [dict(item) for item in self.catalog]

    async def list_notifications(self, *, limit=50, offset=0, unread_only=False, token=None):
        return []


# Test database URL - use in-memory SQLite for tests
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def db_engine():
    """Create a test database engine."""
    engine = create_engine(
        SQLALCHEMY_TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a test database session."""
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=db_engine,
    )
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="function")
def client(db_session):
    """Create a test client with database override."""
    fake_nudging = FakeNudgingClient()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    def override_get_nudging_client():
        return fake_nudging
    
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_nudging_client] = override_get_nudging_client
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    """Mock authentication headers."""
    # Simple JWT token for testing (not validated)
    import base64
    import json
    
    payload = {
        "sub": "test-user-123",
        "email": "test@example.com",
        "name": "Test User"
    }
    
    # Create a simple JWT-like token (header.payload.signature)
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
    payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signature = "test-signature"
    
    token = f"{header}.{payload_encoded}.{signature}"
    
    return {"X-Auth-Request-Access-Token": token}
