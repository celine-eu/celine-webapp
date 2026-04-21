# celine/webapp/api/suggestions.py
"""Suggestions routes — GET /api/suggestions, POST /api/suggestions/{id}/respond."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, cast
import httpx

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, func

from celine.sdk.auth.oidc import OidcClientCredentialsProvider
from celine.webapp.api.deps import DbDep, FlexibilityDep, UserDep
from celine.webapp.api.schemas import (
    BadgeItem,
    FlexibilityCommitmentItem,
    GamificationResponse,
    SuggestionItem,
    SuggestionReminderRequest,
    SuggestionRespondRequest,
    SuccessResponse,
)
from celine.webapp.db.models import SuggestionInteraction, UserBadge
from celine.webapp.settings import settings

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
    db: DbDep,
    flexibility: FlexibilityDep,
) -> list[SuggestionItem]:
    """Return load-shift windows for the authenticated user.

    Delegates to flexibility-api which fetches rec_flexibility_windows via DT,
    filters already-committed suggestions, and caps results.
    """
    try:
        items = await flexibility.list_suggestions()
        async with db as session:
            hidden_ids = set(
                (
                    await session.execute(
                        select(SuggestionInteraction.suggestion_id).where(
                            SuggestionInteraction.user_id == user.sub
                        )
                    )
                ).scalars().all()
            )
        return [
            SuggestionItem(**item.model_dump())
            for item in items
            if item.id not in hidden_ids
        ]
    except Exception as exc:
        logger.warning("Failed to fetch suggestions from flexibility-api: %s", exc)
        return []


def _parse_iso_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid datetime: {value}") from exc


async def _schedule_flexibility_reminder(
    *,
    suggestion_id: str,
    user_id: str,
    period_start: datetime,
    period_end: datetime,
    reward_points: int,
    lang: str | None,
) -> None:
    if not settings.nudging_api_url:
        raise HTTPException(status_code=503, detail="Nudging API not configured")

    client_id = settings.oidc.client_id
    client_secret = settings.oidc.client_secret
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=503,
            detail="OIDC client credentials not configured for nudging reminders",
        )

    provider = OidcClientCredentialsProvider(
        base_url=settings.oidc.base_url,
        client_id=client_id,
        client_secret=client_secret,
        scope=settings.nudging_ingest_scope,
        verify_ssl=settings.oidc.verify_ssl,
    )
    access_token = await provider.get_token()
    trigger_at = period_start - timedelta(minutes=10)
    facts = {
        "facts_version": "1.0",
        "scenario": "flexibility_reminder",
        "suggestion_id": suggestion_id,
        "window_start": period_start.strftime("%H:%M"),
        "window_end": period_end.strftime("%H:%M"),
        "reward_points_estimated": reward_points,
        "period": period_start.date().isoformat(),
        "lang": (lang or "en").split("-")[0],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{settings.nudging_api_url.rstrip('/')}/admin/scheduled-events",
            headers={"Authorization": f"Bearer {access_token.access_token}"},
            json={
                "event_type": "flexibility_reminder",
                "user_id": user_id,
                "external_key": f"flexibility-reminder:{user_id}:{suggestion_id}",
                "trigger_at": trigger_at.astimezone(timezone.utc).isoformat(),
                "facts": facts,
            },
        )
    if response.status_code not in {200, 201}:
        raise HTTPException(
            status_code=502,
            detail="Failed to schedule reminder with nudging tool",
        )


@router.post("/suggestions/{suggestion_id}/remind", response_model=SuccessResponse)
async def suggestion_remind(
    suggestion_id: str,
    body: SuggestionReminderRequest,
    user: UserDep,
    db: DbDep,
) -> SuccessResponse:
    period_start = _parse_iso_datetime(body.period_start)
    period_end = _parse_iso_datetime(body.period_end)
    if period_end <= period_start:
        raise HTTPException(status_code=422, detail="period_end must be after period_start")

    await _schedule_flexibility_reminder(
        suggestion_id=suggestion_id,
        user_id=user.sub,
        period_start=period_start,
        period_end=period_end,
        reward_points=body.reward_points,
        lang=body.lang,
    )

    now = datetime.now(timezone.utc)
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
            existing.response = "reminded"
            existing.period_start = period_start
            existing.period_end = period_end
            existing.responded_at = now
            existing.reward_points = 0
        else:
            session.add(
                SuggestionInteraction(
                    user_id=user.sub,
                    suggestion_id=suggestion_id,
                    suggestion_type="shift-consumption",
                    period_start=period_start,
                    period_end=period_end,
                    responded_at=now,
                    response="reminded",
                    reward_points=0,
                )
            )
        await session.commit()

    return SuccessResponse()


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

    # Delegate commitment creation/rejection and MQTT to flexibility-api
    flex_response = None
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
