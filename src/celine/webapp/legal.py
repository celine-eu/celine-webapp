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

import logging  # noqa: E402
import time  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

import httpx  # noqa: E402

logger = logging.getLogger(__name__)

#: The documents the gate asks to accept, as slots of the legal host.
GATE_DOCUMENTS: tuple[str, ...] = ("terms", "privacy")
REFRESH_SECONDS = 300.0
TIMEOUT_SECONDS = 3.0

_current: dict[str, dict] = {}
_fetched_at: dict[str, float] = {}
_community_of: dict[str, tuple[str | None, float]] = {}


@dataclass
class LegalDocument:
    document: str
    url: str
    version: str | None
    published_at: str | None
    sha256: str | None
    title: str | None
    locale: str | None


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
        documents.append(LegalDocument(
            slot, base_url.rstrip("/") + paths[lang], entry.get("version"), entry.get("published_at"),
            (entry.get("sha256") or {}).get(lang), (entry.get("titles") or {}).get(lang), lang,
        ))
    return documents


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
