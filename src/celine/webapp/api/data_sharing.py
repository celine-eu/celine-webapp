"""Data-sharing routes — a member's own decisions about their energy data.

Behind `DATA_SHARING_ENABLED`, off by default: the dataspace may not be deployed
for some time, and a sharing screen that cannot answer is worse than no screen at
all. When the flag is off every route here answers `404` and the UI hides the
section, so nothing half-working is exposed.

Everything is done **as the member**, with their own verifiable credential. This
service only resolves which credential is theirs.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from celine.webapp.api.deps import UserDep
from celine.webapp.api.schemas import (
    DataSharingDecisionRequest,
    DataSharingHistoryResponse,
    DataSharingStatusResponse,
)
from celine.webapp.services import data_sharing as service
from celine.webapp.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data-sharing", tags=["data-sharing"])


def _require_feature() -> None:
    if not settings.data_sharing_ready:
        # 404 rather than 503: when the feature is off this surface does not
        # exist, and saying "temporarily unavailable" would suggest waiting.
        raise HTTPException(status_code=404, detail="Data sharing is not enabled")


def _member_email(user: UserDep) -> str:
    email = getattr(user, "email", None)
    if not email:
        # The dataspace identity is keyed on the email the participant was
        # onboarded with. Without it there is nothing to resolve.
        raise HTTPException(
            status_code=422, detail="No email address on the current session"
        )
    return email


async def _credential(user: UserDep):
    try:
        return await service.resolve_subject(_member_email(user))
    except service.NoDataspaceIdentity:
        return None
    except service.DataSharingUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("", response_model=DataSharingStatusResponse)
async def get_data_sharing(user: UserDep) -> DataSharingStatusResponse:
    """Every offer, and whether this member has agreed to it.

    Offers come from the published vocabulary rather than a local copy, so what
    is shown here and what the dataspace enforces cannot drift.

    A member with no dataspace identity gets `has_identity: false` and an empty
    list — a normal state for somebody enabled before the integration existed,
    not an error.
    """
    _require_feature()

    credential = await _credential(user)
    if credential is None:
        return DataSharingStatusResponse(has_identity=False, offers=[])

    try:
        offers = await service.list_offers()
        decisions = await service.list_decisions(credential)
    except service.DataSharingUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    granted = {
        d.get("offer_id"): d
        for d in decisions
        if d.get("offer_id") and d.get("status") in {"granted", "approved", "active"}
    }

    merged = []
    for offer in offers:
        offer_id = offer.get("id")
        decision = granted.get(offer_id)
        merged.append(
            {
                **offer,
                "granted": decision is not None,
                # Codes and hashes only — the record of what was shown when the
                # decision was made, never anything about the person.
                "evidence": (decision or {}).get("legal_basis"),
                "decided_at": (decision or {}).get("decided_at"),
            }
        )

    return DataSharingStatusResponse(has_identity=True, offers=merged)


@router.post("/{offer_id}", response_model=DataSharingStatusResponse)
async def set_data_sharing(
    offer_id: str, body: DataSharingDecisionRequest, user: UserDep
) -> DataSharingStatusResponse:
    """Grant or withdraw one offer.

    Withdrawal is the reason this route exists: the onboarding wizard can only
    grant, so without it a consent could be given and never taken back.
    """
    _require_feature()

    credential = await _credential(user)
    if credential is None:
        raise HTTPException(
            status_code=409,
            detail="This account has no dataspace identity yet",
        )

    try:
        await service.set_decision(credential, offer_id, enabled=body.enabled)
    except ValueError as exc:
        # A contract-based offer: disclosed, not toggled.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except service.DataSharingUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return await get_data_sharing(user)


@router.get("/history", response_model=DataSharingHistoryResponse)
async def get_data_sharing_history(user: UserDep) -> DataSharingHistoryResponse:
    """What has happened with this member's data, from their own record.

    Served by provenance under the member's credential, so it is their history
    rather than one this service assembles. Absent provenance returns an empty
    list: the decisions stand without it, and failing here would make the whole
    page unusable for a detail.
    """
    _require_feature()

    credential = await _credential(user)
    if credential is None:
        return DataSharingHistoryResponse(has_identity=False, events=[])

    return DataSharingHistoryResponse(
        has_identity=True, events=await service.list_history(credential)
    )
