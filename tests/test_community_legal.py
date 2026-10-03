"""`GET /api/community` — the legal links: registry link → legal host slot → none."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from celine.webapp.api import community as community_route
from celine.webapp.legal import resolve_link, slot_url
from celine.webapp.settings import settings as app_settings
from tests.fakes import FakeCommunityDetail, FakeRegistryClient

LEGAL = "http://legal.example.org"


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> FakeRegistryClient:
    """The route builds its own client (it bypasses injection), so patch the class."""
    fake = FakeRegistryClient()
    monkeypatch.setattr(community_route, "RecRegistryUserClient", lambda **_: fake)
    monkeypatch.setattr(app_settings, "rec_registry_url", "http://registry.invalid")
    return fake


def _links(client: TestClient, auth_headers: dict) -> dict:
    body = client.get("/api/community", headers=auth_headers).json()
    return {k: body.get(k) for k in ("terms_url", "privacy_url", "statute_url", "regulations_url")}


def test_without_a_legal_host_links_are_the_registrys(client, auth_headers, registry, monkeypatch):
    monkeypatch.setattr(app_settings, "legal_base_url", None)
    registry.community = FakeCommunityDetail(
        key="rec-a", links={"terms": "https://rec-a.example.org/terms", "privacy_policy": ""}
    )
    assert _links(client, auth_headers) == {
        "terms_url": "https://rec-a.example.org/terms",
        "privacy_url": None,
        "statute_url": None,
        "regulations_url": None,
    }


def test_an_empty_link_resolves_to_the_legal_host(client, auth_headers, registry, monkeypatch):
    monkeypatch.setattr(app_settings, "legal_base_url", LEGAL + "/")
    registry.community = FakeCommunityDetail(key="rec-a", links={"privacy_policy": "", "terms": None})
    assert _links(client, auth_headers) == {
        "terms_url": f"{LEGAL}/rec-a/terms/",
        "privacy_url": f"{LEGAL}/rec-a/privacy/",
        "statute_url": f"{LEGAL}/rec-a/statute/",
        "regulations_url": f"{LEGAL}/rec-a/regulations/",
    }


def test_a_registry_link_wins_over_the_legal_host(client, auth_headers, registry, monkeypatch):
    monkeypatch.setattr(app_settings, "legal_base_url", LEGAL)
    registry.community = FakeCommunityDetail(key="rec-a", links={"statute": "https://rec-a.example.org/statute.pdf"})
    links = _links(client, auth_headers)
    assert links["statute_url"] == "https://rec-a.example.org/statute.pdf"
    assert links["privacy_url"] == f"{LEGAL}/rec-a/privacy/"


def test_each_community_gets_its_own_documents(client, auth_headers, registry, monkeypatch):
    monkeypatch.setattr(app_settings, "legal_base_url", LEGAL)
    registry.community = FakeCommunityDetail(key="rec-a")
    first = _links(client, auth_headers)["privacy_url"]
    registry.community = FakeCommunityDetail(key="rec-b")
    assert first == f"{LEGAL}/rec-a/privacy/"
    assert _links(client, auth_headers)["privacy_url"] == f"{LEGAL}/rec-b/privacy/"


def test_no_community_no_legal_link(client, auth_headers, registry, monkeypatch):
    """When the registry cannot say whose member this is, no community's document is shown."""
    monkeypatch.setattr(app_settings, "legal_base_url", LEGAL)
    registry.error = RuntimeError("registry down")
    body = client.get("/api/community", headers=auth_headers).json()
    assert body["key"] == "unknown"
    assert body["privacy_url"] is None and body["terms_url"] is None


def test_slot_addresses_are_safe_for_any_key():
    assert slot_url(LEGAL, "rec a/b", "terms") == f"{LEGAL}/rec%20a%2Fb/terms/"
    assert slot_url(None, "rec-a", "terms") is None
    assert slot_url(LEGAL, None, "terms") is None
    assert resolve_link("   ", LEGAL, "rec-a", "terms") == f"{LEGAL}/rec-a/terms/"
