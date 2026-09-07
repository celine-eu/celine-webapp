"""A member's data-sharing decisions, proxied to onboarding.

This module used to hold a service account on `identity-registry.resolve`, a
credential in request memory, and the merge of published offers against the
decisions the connector held. All of it moved to `../onboarding`, which already
resolved credentials, already spoke to the connector, and already held the
grants. A credential that never leaves the service that resolved it cannot leak
from the one that did not need it.

What is left is a proxy, and the proxy is the point: **the frontend talks only
to this service.** Onboarding is not same-origin, and keeping the browser on one
origin is why this repository exists.

The HTTP is `celine.sdk.onboarding.OnboardingClient`, the same generated-client-
plus-wrapper every other upstream arrives through. What is left here is the one
thing a BFF owns: **which of onboarding's answers a browser is allowed to see.**

* **The member's own token, and no service token.** Onboarding authorises these
  routes by who is asking. Adding a service account here would let this service
  decide somebody else's consent, which is the one thing that would make the
  record worthless.
* **Onboarding's answer about the member is forwarded; anything else is not.**
  A 409 means "there is no decision here to make, and `state` says why" — a real
  answer the UI renders. A 404 would mean this service is calling a surface that
  is not there, which is a deployment fault and must not be confused with the
  404 the feature gate answers when data sharing is switched off.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import HTTPException

from celine.sdk.onboarding import OnboardingApiError, OnboardingClient
from celine.sdk.openapi.onboarding.schemas import (
    DataSharingHistoryResponseSchema,
    DataSharingStatusResponseSchema,
)

logger = logging.getLogger(__name__)

#: The `user_onboarding_views` key under which a dismissal of the sharing banner
#: is recorded. The table already stores "this member has seen page X" with a
#: timestamp, so the prompt needs no table and no migration of its own.
PAGE_KEY = "data-sharing"

#: Statuses that are onboarding's answer *about this member* and belong to the
#: caller unchanged. Everything else is a fault on this side of the seam and
#: becomes a 502, so that "the feature is off" (404) and "the upstream moved"
#: stay distinguishable.
_FORWARDED = frozenset({401, 403, 409, 422, 503})


@asynccontextmanager
async def _forwarding(what: str):
    """Turn onboarding's refusals into the ones this service is allowed to serve."""
    try:
        yield
    except OnboardingApiError as exc:
        status = exc.status_code or 502
        if status in _FORWARDED:
            raise HTTPException(
                status_code=status, detail=exc.detail or str(exc)
            ) from exc
        logger.warning("Onboarding answered %s for %s", status, what)
        raise HTTPException(
            status_code=502, detail=f"Onboarding answered {status}"
        ) from exc
    except httpx.HTTPError as exc:
        # Never reached onboarding at all. Worth retrying, like a 503 from it.
        raise HTTPException(
            status_code=503, detail=f"Onboarding unreachable: {exc}"
        ) from exc


async def get_status(client: OnboardingClient) -> DataSharingStatusResponseSchema:
    """Every offer this member's community publishes, with their decision."""
    async with _forwarding("get_status"):
        return await client.get_data_sharing()


async def set_decision(
    client: OnboardingClient, offer_id: str, *, enabled: bool
) -> DataSharingStatusResponseSchema:
    """Grant or withdraw one offer, as the member."""
    async with _forwarding("set_decision"):
        return await client.set_data_sharing(offer_id, enabled=enabled)


async def get_history(client: OnboardingClient) -> DataSharingHistoryResponseSchema:
    """The member's own record of what happened with their data."""
    async with _forwarding("get_history"):
        return await client.get_data_sharing_history()


# ── the prompt ────────────────────────────────────────────────────────────────
#
# The decisions belong to onboarding. *Being asked* does not: it is per-user
# application state about this app's own UI, which is what this service's
# database is for, and onboarding has no session with the member to hold it.


@dataclass(frozen=True, slots=True)
class Prompt:
    """Whether the banner should appear, and which of the two it is.

    Kept as two facts rather than one flag because the UI is not the same: a
    member who has never been asked gets a short first-run sequence, and one
    whose decision has gone stale gets "you are sharing data, review your
    settings". Collapsing them would make the first-timer read the second.
    """

    #: Has this member ever been asked — by the wizard here, or by deciding
    #: anything at all, including in onboarding's own funnel.
    asked: bool
    #: Has what they last said gone stale.
    review_due: bool


def _as_utc(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; PostgreSQL does not."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _decided_at(offers: list[dict[str, Any]]) -> datetime | None:
    """The newest decision in the merged offers, if any of them carries one."""
    stamps: list[datetime] = []
    for offer in offers:
        raw = offer.get("decided_at")
        if not raw:
            continue
        try:
            stamps.append(_as_utc(datetime.fromisoformat(str(raw))))
        except ValueError:
            # Upstream's format is not this service's to police. An unreadable
            # stamp means "no evidence it was recent", which is the safe way to
            # be wrong: at worst the member is asked once more than needed.
            logger.warning("Unreadable decided_at from onboarding: %r", raw)
    return max(stamps) if stamps else None


def prompt_state(
    *,
    seen_at: datetime | None,
    offers: list[dict[str, Any]],
    after_days: int,
    now: datetime | None = None,
) -> Prompt:
    """Whether to show the banner, from the dismissal and the decisions.

    A decision counts as having been asked even with no dismissal recorded here:
    somebody who consented in onboarding's funnel has been asked, and showing
    them a first-run wizard would be absurd.

    ``after_days`` of zero or less turns the staleness half off, which is how
    "ask once and never again" is configured.
    """
    now = now or datetime.now(timezone.utc)
    decided_at = _decided_at(offers)
    asked = seen_at is not None or decided_at is not None

    if not asked or after_days <= 0:
        return Prompt(asked=asked, review_due=False)

    stamps = [stamp for stamp in (decided_at,) if stamp is not None]
    if seen_at is not None:
        stamps.append(_as_utc(seen_at))

    return Prompt(asked=True, review_due=max(stamps) < now - timedelta(days=after_days))
