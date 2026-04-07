# celine/webapp/api/suggestions.py
"""Suggestions routes — GET /api/suggestions, POST /api/suggestions/{id}/respond."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, cast

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, func

from celine.webapp.api.deps import DbDep, FlexibilityDep, UserDep
from celine.webapp.api.schemas import (
    BadgeItem,
    FlexibilityCommitmentItem,
    GamificationResponse,
    SuggestionItem,
    SuggestionRespondRequest,
)
from celine.webapp.db.models import SuggestionInteraction, UserBadge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["suggestions"])

BADGES: dict[str, dict] = {
    "first-shift":    {"icon": "zap",         "min_actions": 1},
    "peak-saver":     {"icon": "sun",         "min_actions": 5},
    "solar-champion": {"icon": "leaf",        "min_points": 500},
    "streak-3":       {"icon": "trending-up", "streak_days": 3},
}

POINTS_PER_LEVEL = 100



async def _check_and_award_badges(
    session: Any,
    user_id: str,
    total_points: int,
    actions_taken: int,
) -> None:
    """Award any newly unlocked badges."""
    existing_badge_ids = {
        row.badge_id
        for row in (
            await session.execute(select(UserBadge).where(UserBadge.user_id == user_id))
        )
        .scalars()
        .all()
    }
    for badge_id, cfg in BADGES.items():
        if badge_id in existing_badge_ids:
            continue
        unlocked = False
        if "min_actions" in cfg and actions_taken >= cfg["min_actions"]:
            unlocked = True
        if "min_points" in cfg and total_points >= cfg["min_points"]:
            unlocked = True
        if unlocked:
            session.add(UserBadge(user_id=user_id, badge_id=badge_id))


@router.get("/suggestions", response_model=list[SuggestionItem])
async def suggestions(
    user: UserDep,
    flexibility: FlexibilityDep,
) -> list[SuggestionItem]:
    """Return load-shift windows for the authenticated user.

    Delegates to flexibility-api which fetches rec_flexibility_windows via DT,
    filters already-committed suggestions, and caps results.
    """
    try:
        items = await flexibility.list_suggestions()
        return [SuggestionItem(**item.model_dump()) for item in items]
    except Exception as exc:
        logger.warning("Failed to fetch suggestions from flexibility-api: %s", exc)
        return []


@router.post(
    "/suggestions/{suggestion_id}/respond", response_model=GamificationResponse
)
async def suggestion_respond(
    suggestion_id: str,
    body: SuggestionRespondRequest,
    user: UserDep,
    db: DbDep,
    flexibility: FlexibilityDep,
) -> GamificationResponse:
    """Record a user's response to a suggestion.

    Commitment creation and MQTT publishing are delegated to flexibility-api.
    This handler retains gamification points, badges, and interaction tracking.
    """
    now = datetime.now(timezone.utc)
    reward_points = body.reward_points if body.reward_points is not None else 10

    # Delegate commitment creation and MQTT to flexibility-api
    flex_response = None
    if body.response == "accepted":
        try:
            flex_response = await flexibility.respond_to_suggestion(
                suggestion_id,
                body.response,
                reward_points=reward_points,
                period_start=body.period_start,
                period_end=body.period_end,
            )
        except Exception as exc:
            logger.warning(
                "flexibility-api respond failed for suggestion=%s: %s", suggestion_id, exc
            )

    async with db as session:
        existing = (
            await session.execute(
                select(SuggestionInteraction).where(
                    SuggestionInteraction.user_id == user.sub,
                    SuggestionInteraction.suggestion_id == suggestion_id,
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.response = body.response
            existing.responded_at = now
        else:
            session.add(
                SuggestionInteraction(
                    user_id=user.sub,
                    suggestion_id=suggestion_id,
                    suggestion_type="shift-consumption",
                    period_start=now,
                    period_end=now + timedelta(hours=1),
                    responded_at=now,
                    response=body.response,
                    reward_points=reward_points if body.response == "accepted" else 0,
                )
            )

        actions_taken = (
            await session.execute(
                select(func.count()).where(
                    SuggestionInteraction.user_id == user.sub,
                    SuggestionInteraction.response == "accepted",
                )
            )
        ).scalar() or 0

        if body.response == "accepted" and not existing:
            actions_taken += 1

        await _check_and_award_badges(session, user.sub, 0, actions_taken)
        await session.commit()

        badge_rows = (
            (
                await session.execute(
                    select(UserBadge).where(UserBadge.user_id == user.sub)
                )
            )
            .scalars()
            .all()
        )

        badges = [
            BadgeItem(
                badge_id=b.badge_id,
                icon=BADGES.get(b.badge_id, {}).get("icon", "zap"),
                earned_at=b.earned_at.isoformat(),
            )
            for b in badge_rows
        ]

    commitment_item: FlexibilityCommitmentItem | None = None
    if flex_response and flex_response.commitment_id is not None:
        commitment_item = FlexibilityCommitmentItem(
            id=str(flex_response.commitment_id),
            suggestion_id=suggestion_id,
            status=cast(Literal["committed", "settled", "rejected", "cancelled"], flex_response.status.value),
            period_end=body.period_end or now.isoformat(),
            reward_points_estimated=flex_response.reward_points_estimated,
            reward_points_actual=None,
            committed_at=now.isoformat(),
            settled_at=None,
        )

    # total_points/level are omitted here — client should reload from GET /gamification
    # for accurate totals (base points from rec_participant_points + active from flexibility-api).
    return GamificationResponse(
        total_points=0,
        level=1,
        next_level_at=POINTS_PER_LEVEL,
        badges=badges,
        actions_taken=actions_taken,
        pending_commitment=commitment_item,
    )


@router.delete("/commitments/{commitment_id}", status_code=204)
async def cancel_commitment(
    commitment_id: str,
    user: UserDep,
    flexibility: FlexibilityDep,
) -> None:
    """Cancel a pending flexibility commitment.

    Proxies to flexibility-api which enforces ownership and status checks.
    """
    import uuid as _uuid
    try:
        cid = _uuid.UUID(commitment_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Commitment not found")
    try:
        await flexibility.cancel_commitment(cid)
    except Exception as exc:
        logger.warning("cancel_commitment failed for id=%s: %s", commitment_id, exc)
        raise HTTPException(status_code=404, detail="Commitment not found or not cancellable")
