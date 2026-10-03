"""The terms gate per community document (`celine.webapp.legal`, `/api/me`, `/api/terms/accept`).

The legal host's `current.json` and the member's community are faked; nothing here touches
a network.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from celine.webapp import legal
from celine.webapp.settings import settings as app_settings

BASE = "http://legal.example.org"


def _current(terms="0.1", privacy="0.1", published="2026-01-01T00:00:00Z"):
    def slot(name, version):
        return {"id": f"rec-a/{name}", "version": version, "status": "final", "published_at": published,
                "paths": {"it": f"/rec-a/{name}/{version}/it/", "en": f"/rec-a/{name}/{version}/en/"},
                "sha256": {"it": "a" * 64, "en": "b" * 64}, "titles": {"it": name.title(), "en": name.title()}}
    slots = {"terms": slot("terms", terms), "privacy": slot("privacy", privacy)}
    return {"owner": "rec-a", "env": "local", "slots": slots}


@pytest.fixture
def host(monkeypatch):
    """A legal host whose answer each test sets; the member's community is rec-a."""
    monkeypatch.setattr(app_settings, "legal_base_url", BASE)
    monkeypatch.setattr(legal, "_current", {})
    monkeypatch.setattr(legal, "_fetched_at", {"rec-a": time.monotonic()})  # never refetched

    async def community(user_sub, token, registry_url):
        return "rec-a"

    monkeypatch.setattr(legal, "community_key_of", community)

    def answer(body):
        if body is None:
            legal._current.pop("rec-a", None)
        else:
            legal._current["rec-a"] = body

    return answer


def _me(client, auth_headers):
    response = client.get("/api/me", headers={**auth_headers, "Accept-Language": "it-IT,it;q=0.9"})
    assert response.status_code == 200
    return response.json()


def _accept(client, auth_headers, documents):
    return client.post("/api/terms/accept", headers=auth_headers, json={"accept": True, "documents": documents})


# ── the rules ────────────────────────────────────────────────────────────────


def test_before_the_host_answers_each_document_is_its_slot_address_without_version():
    docs = legal.gate_documents(BASE, "rec-a", None, ["it"])
    assert [(d.document, d.url, d.version) for d in docs] == [
        ("terms", f"{BASE}/rec-a/terms/", None),
        ("privacy", f"{BASE}/rec-a/privacy/", None),
    ]


def test_from_the_host_the_page_in_the_members_language():
    docs = legal.gate_documents(BASE, "rec-a", _current(), ["en", "it"])
    assert docs[0].url == f"{BASE}/rec-a/terms/0.1/en/" and docs[0].locale == "en" and docs[0].sha256 == "b" * 64
    only_terms = {"slots": {"terms": _current()["slots"]["terms"]}}
    assert [d.document for d in legal.gate_documents(BASE, "rec-a", only_terms, ["it"])] == ["terms"]


def test_when_a_document_must_be_accepted():
    doc = legal.gate_documents(BASE, "rec-a", _current(terms="0.2", published="2026-03-01T00:00:00Z"), ["it"])[0]
    at = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)  # noqa: E731
    assert legal.needs_acceptance(doc, None, None, has_row=False)
    assert legal.needs_acceptance(doc, "0.1", at("2026-02-01T00:00:00"), True)
    assert not legal.needs_acceptance(doc, "0.2", at("2026-03-02T00:00:00"), True)
    # Accepted without a version: the date against the publication decides.
    assert legal.needs_acceptance(doc, None, at("2026-02-01T00:00:00"), True)
    assert not legal.needs_acceptance(doc, None, at("2026-03-02T00:00:00"), True)
    unknown = legal.gate_documents(BASE, "rec-a", None, ["it"])[0]
    assert not legal.needs_acceptance(unknown, "0.1", at("2026-01-02T00:00:00"), True)


def test_locales_in_the_clients_order():
    assert legal.locales_from("it-IT,it;q=0.9,en;q=0.8") == ["it", "en"]
    assert legal.locales_from(None) == []


# ── the API ─────────────────────────────────────────────────────────────────


def test_each_document_is_accepted_and_asked_again_only_when_it_changes(client: TestClient, auth_headers, host):
    host(_current())
    me = _me(client, auth_headers)
    assert me["terms_required"] is True
    assert [(d["document"], d["version"], d["required"]) for d in me["legal_documents"]] == [
        ("terms", "0.1", True), ("privacy", "0.1", True)]
    assert me["legal_documents"][0]["url"] == f"{BASE}/rec-a/terms/0.1/it/"

    assert _accept(client, auth_headers, [{"document": "terms", "version": "0.1"},
                                          {"document": "privacy", "version": "0.1"}]).status_code == 200
    assert _me(client, auth_headers)["terms_required"] is False

    host(_current(terms="0.2", published="2026-03-01T00:00:00Z"))
    me = _me(client, auth_headers)
    assert me["terms_required"] is True
    assert {d["document"]: d["required"] for d in me["legal_documents"]} == {"terms": True, "privacy": False}
    assert _accept(client, auth_headers, [{"document": "terms", "version": "0.2"}]).status_code == 200
    assert _me(client, auth_headers)["terms_required"] is False


def test_a_stale_page_is_refused(client: TestClient, auth_headers, host):
    host(_current(terms="0.2"))
    response = _accept(client, auth_headers, [{"document": "terms", "version": "0.1"}])
    assert response.status_code == 409 and "0.2" in response.json()["detail"]
    assert _me(client, auth_headers)["terms_required"] is True  # nothing was recorded


def test_before_the_host_answers_the_date_tracks_the_version(client: TestClient, auth_headers, host):
    host(None)  # the host has never answered
    me = _me(client, auth_headers)
    assert [d["version"] for d in me["legal_documents"]] == [None, None] and me["terms_required"] is True
    assert _accept(client, auth_headers, [{"document": "terms"}, {"document": "privacy"}]).status_code == 200
    assert _me(client, auth_headers)["terms_required"] is False  # accepted; nothing newer is known

    # The host answers: a version published before the acceptance is the one accepted…
    host(_current(published="2020-01-01T00:00:00Z"))
    assert _me(client, auth_headers)["terms_required"] is False
    # …one published after it is new, and is asked.
    host(_current(published="2999-01-01T00:00:00Z"))
    assert _me(client, auth_headers)["terms_required"] is True


def test_without_a_community_the_global_policy_still_applies(client: TestClient, auth_headers, monkeypatch):
    monkeypatch.setattr(app_settings, "legal_base_url", BASE)

    async def nobody(user_sub, token, registry_url):
        return None

    monkeypatch.setattr(legal, "community_key_of", nobody)
    me = _me(client, auth_headers)
    assert me["legal_documents"] is None and me["terms_required"] is True
    assert client.post("/api/terms/accept", headers=auth_headers, json={"accept": True}).status_code == 200
    assert _me(client, auth_headers)["terms_required"] is False
