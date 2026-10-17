"""The terms gate per community document (`celine.webapp.legal`, `/api/me`, `/api/terms/accept`).

The legal host's `current.json` and the member's community are faked; nothing here touches
a network.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx
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
    # No onboarding unless a test says so: the pull on a miss is its own section below.
    monkeypatch.setattr(app_settings, "onboarding_api_url", None)
    monkeypatch.setattr(legal, "_onboarding_of", {})

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


# ── the terms' clauses: a separate act (Art. 1341(2) c.c.) ───────────────────

DECLARATIONS = {
    "it": {"general": "Dichiaro di accettare le Condizioni d'uso, versione 0.2.",
           "specific_approval": {"text": "Ai sensi degli artt. 1341 e 1342 c.c., approvo gli artt. 5 e 7.",
                                 "articles": [5, 7]}},
    "en": {"general": "I accept the Terms of use, version 0.2."},
}


def _with_clauses(terms="0.2", declarations=DECLARATIONS, **kw):
    body = _current(terms=terms, **kw)
    if declarations is not None:
        body["slots"]["terms"]["declarations"] = declarations
    return body


def test_the_clauses_are_the_terms_page_with_their_own_words():
    terms, clauses, privacy = legal.gate_documents(BASE, "rec-a", _with_clauses(), ["it"])
    assert [terms.document, clauses.document, privacy.document] == ["terms", "terms_clauses", "privacy"]
    assert (clauses.url, clauses.version, clauses.sha256) == (terms.url, terms.version, terms.sha256)
    assert terms.declaration == DECLARATIONS["it"]["general"]
    assert clauses.declaration == DECLARATIONS["it"]["specific_approval"]["text"]
    assert privacy.declaration is None


def test_no_words_no_box():
    """A text without `specific_approval` in the language shown, or no text yet: not asked."""
    english = legal.gate_documents(BASE, "rec-a", _with_clauses(), ["en"])
    assert [d.document for d in english] == ["terms", "privacy"]
    assert english[0].declaration == DECLARATIONS["en"]["general"]
    assert "terms_clauses" not in [d.document for d in legal.gate_documents(BASE, "rec-a", _current(), ["it"])]
    assert "terms_clauses" not in [d.document for d in legal.gate_documents(BASE, "rec-a", None, ["it"])]


def test_the_gate_asks_both_and_shows_the_words(client: TestClient, auth_headers, host):
    host(_with_clauses())
    docs = {d["document"]: d for d in _me(client, auth_headers)["legal_documents"]}
    assert docs["terms"]["declaration"] == DECLARATIONS["it"]["general"]
    assert docs["terms_clauses"]["declaration"].startswith("Ai sensi")
    assert docs["terms_clauses"]["required"] is True


def test_the_clauses_are_never_implied_by_accepting_the_rest(client: TestClient, auth_headers, host):
    host(_with_clauses())
    response = _accept(client, auth_headers, [{"document": "terms", "version": "0.2"},
                                              {"document": "privacy", "version": "0.1"}])
    assert response.status_code == 422 and "terms_clauses" in response.json()["detail"]
    assert all(d["required"] for d in _me(client, auth_headers)["legal_documents"])  # nothing recorded


def test_each_is_recorded_on_its_own(client: TestClient, auth_headers, host, db_url):
    host(_with_clauses())
    assert _accept(client, auth_headers, [{"document": "terms", "version": "0.2"},
                                          {"document": "terms_clauses", "version": "0.2"},
                                          {"document": "privacy", "version": "0.1"}]).status_code == 200
    rows = _rows(db_url)
    assert sorted(r["document"] for r in rows) == ["privacy", "terms", "terms_clauses"]
    clauses = next(r for r in rows if r["document"] == "terms_clauses")
    assert clauses["policy_version"] == "0.2" and clauses["document_sha256"] == "a" * 64
    assert clauses["source"] is None
    assert _me(client, auth_headers)["terms_required"] is False


def test_a_member_who_accepted_the_terms_is_asked_the_clauses_alone(client: TestClient, auth_headers, host):
    """Decision 3: existing members approve box 2 at their next login, and only box 2."""
    host(_current(terms="0.2"))  # the terms before they carried the box
    assert _accept(client, auth_headers, [{"document": "terms", "version": "0.2"},
                                          {"document": "privacy", "version": "0.1"}]).status_code == 200
    host(_with_clauses())  # the same version, now with the words
    required = {d["document"]: d["required"] for d in _me(client, auth_headers)["legal_documents"]}
    assert required == {"terms": False, "terms_clauses": True, "privacy": False}
    assert _accept(client, auth_headers, [{"document": "terms_clauses", "version": "0.2"}]).status_code == 200
    assert _me(client, auth_headers)["terms_required"] is False


# ── accepted once: the pull from onboarding on a miss ────────────────────────

SUBMISSION = "6f1c1d7e-0000-4000-8000-000000000001"


def _rows(db_url):
    import sqlite3

    with sqlite3.connect(db_url.split("///", 1)[1]) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM policy_acceptance ORDER BY id")]


def _acceptance(slot, version="0.2", sha="a" * 64, legal_slot=None):
    return {"slot": slot, "legal_slot": legal_slot or slot, "version": version,
            "url": f"https://legal.example.org/rec-a/{slot}/", "sha256": sha,
            "accepted_at": "2026-10-17T09:00:00Z"}


@pytest.fixture
def onboarding(monkeypatch, mock_upstream_http):
    """Onboarding answering `/api/me/acceptances` with what a test sets."""
    monkeypatch.setattr(app_settings, "onboarding_api_url", "http://onboarding.test")

    def install(acceptances, status=200, submission_id=SUBMISSION):
        body = ({"submission_id": submission_id, "rec_slug": "rec-a", "acceptances": acceptances}
                if status == 200 else {"detail": "refused"})
        return mock_upstream_http(lambda request: httpx.Response(status, json=body))

    return install


def test_what_was_accepted_at_application_is_not_asked_again(client, auth_headers, host, onboarding, db_url):
    host(_with_clauses())
    seen = onboarding([_acceptance("terms"), _acceptance("terms_clauses"),
                       _acceptance("gdpr", version="0.1", legal_slot="privacy")])

    me = _me(client, auth_headers)

    assert me["terms_required"] is False
    assert seen[0].url.path == "/api/me/acceptances"
    assert seen[0].headers["authorization"] == f"Bearer {auth_headers[app_settings.jwt_header_name]}"
    rows = _rows(db_url)
    assert sorted(r["document"] for r in rows) == ["privacy", "terms", "terms_clauses"]
    assert {r["source"] for r in rows} == {"onboarding"}
    assert {r["source_ref"] for r in rows} == {SUBMISSION}
    terms = next(r for r in rows if r["document"] == "terms")
    assert terms["policy_version"] == "0.2" and terms["locale"] == "it" and terms["accepted_from_ip"] is None
    assert terms["accepted_at"].startswith("2026-10-17")


def test_an_acceptance_in_another_language_of_the_same_text_counts(client, auth_headers, host, onboarding, db_url):
    host(_with_clauses())
    onboarding([_acceptance("terms", sha="b" * 64)])  # the English text of 0.2

    required = {d["document"]: d["required"] for d in _me(client, auth_headers)["legal_documents"]}

    assert required["terms"] is False
    assert next(r for r in _rows(db_url) if r["document"] == "terms")["locale"] == "en"


@pytest.mark.parametrize("acceptance", [
    _acceptance("terms", version="0.1"),          # an older version
    _acceptance("terms", sha="c" * 64),           # the same version, another text
    _acceptance("terms", sha=None),               # no sha256: which text is unknown
    _acceptance("terms", version=None),           # no version
])
def test_anything_but_the_exact_text_is_asked(client, auth_headers, host, onboarding, db_url, acceptance):
    host(_with_clauses())
    onboarding([acceptance])

    required = {d["document"]: d["required"] for d in _me(client, auth_headers)["legal_documents"]}

    assert required["terms"] is True
    assert _rows(db_url) == []


def test_the_terms_accepted_at_application_do_not_stand_for_the_clauses(client, auth_headers, host, onboarding):
    host(_with_clauses())
    onboarding([_acceptance("terms")])

    required = {d["document"]: d["required"] for d in _me(client, auth_headers)["legal_documents"]}

    assert required == {"terms": False, "terms_clauses": True, "privacy": True}


@pytest.mark.parametrize("status", [403, 409, 500, 503])
def test_onboarding_refusing_or_down_means_asked(client, auth_headers, host, onboarding, db_url, status):
    host(_with_clauses())
    onboarding([], status=status)

    assert _me(client, auth_headers)["terms_required"] is True
    assert _rows(db_url) == []


def test_no_application_means_asked(client, auth_headers, host, onboarding, db_url):
    host(_with_clauses())
    onboarding([], submission_id=None)

    assert _me(client, auth_headers)["terms_required"] is True
    assert _rows(db_url) == []


def test_before_the_host_answers_onboarding_is_not_asked(client, auth_headers, host, onboarding):
    """No version to match: nothing could be copied, so nothing is asked of onboarding."""
    host(None)
    seen = onboarding([_acceptance("terms")])

    assert _me(client, auth_headers)["terms_required"] is True
    assert seen == []


def test_onboarding_is_asked_once_per_member_for_a_while(client, auth_headers, host, onboarding):
    host(_with_clauses())
    seen = onboarding([], status=503)

    _me(client, auth_headers)
    _me(client, auth_headers)

    assert len(seen) == 1


def test_without_onboarding_nothing_is_asked_of_it(client, auth_headers, host, mock_upstream_http):
    host(_with_clauses())
    seen = mock_upstream_http(lambda request: httpx.Response(500))

    assert _me(client, auth_headers)["terms_required"] is True
    assert seen == []
