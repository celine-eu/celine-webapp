"""Data-sharing routes — a member's own decisions about their energy data.

Behind `DATA_SHARING_ENABLED`, off by default: the dataspace may not be deployed
for some time, and a sharing screen that cannot answer is worse than no screen at
all. When the flag is off every route here answers `404` and the UI hides the
section, so nothing half-working is exposed.

**These are proxies.** Onboarding owns the member's dataspace identity, resolves
their credential and holds the connector grants; this service forwards the
member's own token — through `celine.sdk.onboarding`, like every other upstream —
and passes the answer back. The paths and response shapes are unchanged from when
the work happened here, because the one consumer has a page built on them and a
relocation should cost it nothing.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from celine.webapp.api.deps import DbDep, OnboardingDep, UserDep
from celine.webapp.api.schemas import (
    DataSharingDecisionRequest,
    DataSharingHistoryResponse,
    DataSharingStatusResponse,
)
from celine.webapp.db.user_settings import get_onboarding_page_seen_at
from celine.webapp.services import data_sharing as service
from celine.webapp.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data-sharing", tags=["data-sharing"])


def _state(answer) -> str | None:
    """Onboarding's `state` as the word itself.

    The SDK hands back the generated enum; the page reads a string, and putting
    the enum in the response would leak the generated class's name into JSON on
    a future serializer change.
    """
    state = getattr(answer, "state", None)
    return getattr(state, "value", state)


async def _status(answer, user: UserDep, db: DbDep) -> DataSharingStatusResponse:
    """Onboarding's answer, plus the two facts the banner needs.

    Being *asked* is this service's to know: it is per-user state about this
    app's own UI, and onboarding holds no session with the member to keep it in.
    It is read from `user_onboarding_views` under `data-sharing`, the same table
    and the same route (`POST /api/onboarding/seen`) every in-app tour uses.
    """
    offers = answer.offers or []
    prompt = service.prompt_state(
        seen_at=await get_onboarding_page_seen_at(user.sub, service.PAGE_KEY, db),
        offers=offers,
        after_days=settings.data_sharing_review_after_days,
    )
    return DataSharingStatusResponse(
        has_identity=answer.has_identity,
        state=_state(answer),
        offers=offers,
        asked=prompt.asked,
        review_due=prompt.review_due,
    )


def _require_feature() -> None:
    if not settings.data_sharing_ready:
        # 404 rather than 503: when the feature is off this surface does not
        # exist, and saying "temporarily unavailable" would suggest waiting.
        raise HTTPException(status_code=404, detail="Data sharing is not enabled")


@router.get("", response_model=DataSharingStatusResponse)
async def get_data_sharing(
    user: UserDep, onboarding: OnboardingDep, db: DbDep
) -> DataSharingStatusResponse:
    """Every offer this member's community publishes, and their decision on it.

    A member with no dataspace identity gets `has_identity: false` and an empty
    list — a normal state, not an error. `state` says which normal state it is:
    a community that does not take part and a member not yet provisioned need
    different sentences, and used to get the same one.

    `asked` and `review_due` are what the banner is drawn from: nobody has been
    asked until they are, and a consent nobody ever revisits is the thing
    GDPR Art. 7(3) is suspicious of.

    The token is verified here before it is forwarded, as on every other route.
    Onboarding verifies it again, and neither service relies on the other having
    done so.
    """
    _require_feature()

    return await _status(await service.get_status(onboarding), user, db)


@router.post("/{offer_id}", response_model=DataSharingStatusResponse)
async def set_data_sharing(
    offer_id: str,
    body: DataSharingDecisionRequest,
    user: UserDep,
    onboarding: OnboardingDep,
    db: DbDep,
) -> DataSharingStatusResponse:
    """Grant or withdraw one offer.

    Withdrawal is the reason this route exists: the onboarding wizard can only
    grant, so without it a consent could be given and never taken back.

    Onboarding answers 409 when there is no decision to make — an offer this REC
    does not publish, one disclosed under a contract rather than consented to, or
    a member with no identity yet — and that refusal is forwarded with the reason
    it gave.
    """
    _require_feature()

    answer = await service.set_decision(onboarding, offer_id, enabled=body.enabled)
    return await _status(answer, user, db)


@router.get("/history", response_model=DataSharingHistoryResponse)
async def get_data_sharing_history(
    user: UserDep, onboarding: OnboardingDep
) -> DataSharingHistoryResponse:
    """What has happened with this member's data, from their own record.

    Served by provenance under the member's credential, so it is their history
    rather than one this service assembles. Absent provenance is an empty list
    rather than a failure — decided upstream, where the credential is.
    """
    _require_feature()

    answer = await service.get_history(onboarding)
    return DataSharingHistoryResponse(
        has_identity=answer.has_identity,
        state=_state(answer),
        events=answer.events or [],
    )
