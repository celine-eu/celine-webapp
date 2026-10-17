"""Where a community's legal documents are, when the registry does not say.

A legal host serves every community's documents at one address per *slot*:
`<LEGAL_BASE_URL>/<community key>/<slot>/` always shows the slot's current version. So a
link the rec-registry leaves empty still resolves, and a new community needs no link
written anywhere. The rule, per link:

1. the community's own registry link, when it is set (an operator can always point one
   community elsewhere);
2. otherwise the legal host's slot address, when `LEGAL_BASE_URL` is set;
3. otherwise nothing: the frontend keeps its own fallback, exactly as before.

`LEGAL_BASE_URL` is empty by default, so a deployment without a legal host behaves as it
always has.
"""

from __future__ import annotations

from urllib.parse import quote

# The rec-registry's `community.links` key → the legal host's slot.
REGISTRY_LINK_SLOTS: dict[str, str] = {
    "privacy_policy": "privacy",
    "terms": "terms",
    "statute": "statute",
    "regulations": "regulations",
}


def slot_url(base_url: str | None, community_key: str | None, slot: str) -> str | None:
    """`<base>/<community>/<slot>/`, or None without a base or a community."""
    if not base_url or not community_key:
        return None
    return f"{base_url.rstrip('/')}/{quote(community_key, safe='')}/{slot}/"


def resolve_link(
    registry_value: object, base_url: str | None, community_key: str | None, registry_key: str
) -> str | None:
    """The link to show for one registry key, by the rule in this module's docstring."""
    explicit = str(registry_value).strip() if registry_value is not None else ""
    if explicit:
        return explicit
    return slot_url(base_url, community_key, REGISTRY_LINK_SLOTS[registry_key])


# ── Accepting the community's documents ──────────────────────────────────────
#
# With a legal host, the terms gate asks for the member's own community's documents
# (`GATE_DOCUMENTS`), each with its own version, instead of one `POLICY_VERSION` for the
# whole deployment. Per document, the member is asked when:
#
# - they have never accepted it in this community; or
# - the current version is known and differs from the one they accepted; or
# - their acceptance carries no version (the host had not answered) and is older than
#   the current version's publication.
#
# Before the host has ever answered, a document's version is unknown: the gate asks only
# members who have never accepted it, and records the acceptance with its date and no
# version (the host's dated history says which version that was). `current.json` is
# refreshed every few minutes and the last good copy kept while the host is down.
#
# `terms_clauses` is the specific approval of the terms' onerous clauses (Art. 1341(2)
# c.c.): the terms' own page, version and sha256, asked as a separate act only when the
# text carries the words for it (`declarations.<lang>.specific_approval`). It is recorded
# on its own row, so a member who accepted the terms is asked the approval alone.
#
# **Accepted once, at application.** A document the member has not accepted here may have
# been accepted in onboarding's form. On such a miss the gate asks onboarding, with the
# member's own token, and copies an acceptance whose version **and** sha256 match the text
# the host serves now, marked as coming from onboarding with the submission id. Anything
# else is asked: no match, onboarding unset or down, no application.

import logging  # noqa: E402
import time  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from typing import Any  # noqa: E402

import httpx  # noqa: E402

logger = logging.getLogger(__name__)

#: The documents the gate asks to accept, as slots of the legal host.
GATE_DOCUMENTS: tuple[str, ...] = ("terms", "terms_clauses", "privacy")
#: The approval of the terms' clauses: given on the terms' text, its own record.
CLAUSES, CLAUSES_OF = "terms_clauses", "terms"
#: `policy_acceptance.source` of a row copied from onboarding's application.
FROM_ONBOARDING = "onboarding"
REFRESH_SECONDS = 300.0
TIMEOUT_SECONDS = 3.0

_current: dict[str, dict] = {}
_fetched_at: dict[str, float] = {}
_community_of: dict[str, tuple[str | None, float]] = {}
_onboarding_of: dict[str, tuple["Accepted | None", float]] = {}


@dataclass
class LegalDocument:
    document: str
    url: str
    version: str | None
    published_at: str | None
    sha256: str | None
    title: str | None
    locale: str | None
    #: What the member declares, in the text's own words: `general` for the terms,
    #: `specific_approval.text` for their clauses. None for a text that has none.
    declaration: str | None = None
    #: The sha256 of the text in every language the host publishes it in: an acceptance
    #: made in another language is of the same version.
    sha256_by_lang: dict[str, str] | None = None


@dataclass
class Accepted:
    """What the member accepted at application, as onboarding recorded it."""

    submission_id: str
    by_slot: dict[str, Any]  # legal slot → the SDK's AcceptanceReadSchema


async def current(base_url: str, community_key: str, client: httpx.AsyncClient | None = None) -> dict | None:
    """The community's `current.json`: fetched when due, the last good copy otherwise."""
    if time.monotonic() - _fetched_at.get(community_key, -REFRESH_SECONDS) >= REFRESH_SECONDS:
        _fetched_at[community_key] = time.monotonic()
        url = f"{base_url.rstrip('/')}/{quote(community_key, safe='')}/current.json"
        try:
            if client is None:
                async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as own:
                    response = await own.get(url)
            else:
                response = await client.get(url)
            response.raise_for_status()
            body = response.json()
            if isinstance(body, dict) and isinstance(body.get("slots"), dict):
                _current[community_key] = body
        except Exception as exc:
            logger.warning("legal host: %s unavailable (%s)", url, exc)
    return _current.get(community_key)


def gate_documents(base_url: str, community_key: str, known: dict | None, locales: list[str]) -> list[LegalDocument]:
    """The documents to accept, from `current.json` (or their slot addresses before it). Pure."""
    documents = []
    for slot in GATE_DOCUMENTS:
        if slot == CLAUSES:
            clauses = _clauses_of(next((d for d in documents if d.document == CLAUSES_OF), None),
                                  (known or {}).get("slots", {}).get(CLAUSES_OF))
            if clauses is not None:
                documents.append(clauses)
            continue
        if known is None:
            documents.append(LegalDocument(slot, slot_url(base_url, community_key, slot), None, None, None, None, None))
            continue
        entry = (known.get("slots") or {}).get(slot)
        if not entry:
            continue  # the community has no such document: nothing to accept
        if entry.get("external"):
            if entry.get("url"):
                documents.append(LegalDocument(slot, entry["url"], entry.get("version"), entry.get("captured"),
                                               entry.get("sha256"), entry.get("title"), None))
            continue
        paths = entry.get("paths") or {}
        lang = next((lang for lang in locales if lang in paths), next(iter(paths), None))
        if lang is None:
            continue
        declarations = (entry.get("declarations") or {}).get(lang) or {}
        documents.append(LegalDocument(
            slot, base_url.rstrip("/") + paths[lang], entry.get("version"), entry.get("published_at"),
            (entry.get("sha256") or {}).get(lang), (entry.get("titles") or {}).get(lang), lang,
            declaration=declarations.get("general") if isinstance(declarations, dict) else None,
            sha256_by_lang=dict(entry.get("sha256") or {}),
        ))
    return documents


def _clauses_of(terms: LegalDocument | None, entry: dict | None) -> LegalDocument | None:
    """The approval of the terms' clauses, on the terms' page: only with its words. Pure."""
    if terms is None or not entry or terms.locale is None:
        return None
    approval = ((entry.get("declarations") or {}).get(terms.locale) or {}).get("specific_approval")
    if not isinstance(approval, dict) or not approval.get("text"):
        return None  # no words, no box
    return LegalDocument(CLAUSES, terms.url, terms.version, terms.published_at, terms.sha256, terms.title,
                         terms.locale, declaration=approval["text"], sha256_by_lang=terms.sha256_by_lang)


def accepted_at_application(document: LegalDocument, accepted: Accepted | None):
    """Onboarding's acceptance of exactly this text, if it has one. Pure.

    The version must be the one served now, and the sha256 that of the text in one of the
    languages it is published in. Without both on either side nothing matches: a version
    alone does not say which text was read.
    """
    if accepted is None or document.version is None or not document.sha256_by_lang:
        return None
    found = accepted.by_slot.get(document.document)
    if found is None or not found.version or not found.sha256:
        return None
    if str(found.version) != document.version or found.sha256 not in document.sha256_by_lang.values():
        return None
    return found


def language_of(document: LegalDocument, sha256: str) -> str | None:
    """The language whose text has *sha256*. Pure."""
    return next((lang for lang, sha in (document.sha256_by_lang or {}).items() if sha == sha256), None)


async def onboarding_acceptances(user_sub: str, token: str | None, onboarding_url: str | None) -> Accepted | None:
    """What the member accepted at application, from onboarding, cached for a few minutes.

    Read with the member's own token. None when onboarding is not configured, does not
    answer, or holds no application for them: the gate then asks.
    """
    if not token or not onboarding_url:
        return None
    cached = _onboarding_of.get(user_sub)
    if cached and time.monotonic() - cached[1] < REFRESH_SECONDS:
        return cached[0]
    found: Accepted | None = None
    try:
        from celine.sdk.onboarding import OnboardingClient

        answer = await OnboardingClient(onboarding_url, default_token=token,
                                        timeout=TIMEOUT_SECONDS).get_acceptances()
        if answer.submission_id:
            found = Accepted(str(answer.submission_id), {a.legal_slot: a for a in answer.acceptances or []})
    except Exception as exc:
        # Cached too: a deployment without onboarding must not wait on it at every request.
        logger.warning("legal gate: onboarding's acceptances of %s unknown (%s)", user_sub, exc)
    _onboarding_of[user_sub] = (found, time.monotonic())
    return found


def needs_acceptance(document: LegalDocument, accepted_version: str | None, accepted_at: datetime | None,
                     has_row: bool) -> bool:
    """Whether the member must accept this document (again). Pure."""
    if not has_row:
        return True
    if document.version is not None and accepted_version is not None:
        return accepted_version != document.version
    if accepted_version is None and document.published_at and accepted_at is not None:
        published = datetime.fromisoformat(document.published_at.replace("Z", "+00:00"))
        if accepted_at.tzinfo is None:  # stored in UTC; some drivers drop the zone
            accepted_at = accepted_at.replace(tzinfo=timezone.utc)
        return accepted_at < published
    return False


def locales_from(accept_language: str | None) -> list[str]:
    """`it-IT,it;q=0.9,en;q=0.8` → `["it", "en"]`, in the client's order."""
    seen: list[str] = []
    for part in (accept_language or "").split(","):
        lang = part.split(";")[0].strip().split("-")[0].lower()
        if lang and lang not in seen:
            seen.append(lang)
    return seen


async def community_key_of(user_sub: str, token: str | None, registry_url: str | None) -> str | None:
    """The member's community key, from the rec-registry, cached for a few minutes."""
    cached = _community_of.get(user_sub)
    if cached and time.monotonic() - cached[1] < REFRESH_SECONDS:
        return cached[0]
    key = None
    if token and registry_url:
        try:
            from celine.sdk.rec_registry import RecRegistryUserClient

            detail = await RecRegistryUserClient(base_url=registry_url, default_token=token).get_my_community()
            key = str(detail.key) if detail is not None and detail.key else None
        except Exception as exc:
            logger.warning("legal gate: community of %s unknown (%s)", user_sub, exc)
            return None  # not cached: try again next time
    _community_of[user_sub] = (key, time.monotonic())
    return key
