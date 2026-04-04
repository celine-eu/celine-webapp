# celine/webapp/api/suggestions.py
"""Suggestions routes — GET /api/suggestions, POST /api/suggestions/{id}/respond."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, cast

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, func

from celine.sdk.openapi.dt.models import UserMembershipSchema
from celine.webapp.api.deps import DbDep, DTDep, UserDep
from celine.webapp.api.schemas import (
    BadgeItem,
    FlexibilityCommitmentItem,
    GamificationResponse,
    SuggestionItem,
    SuggestionRespondRequest,
)
from celine.webapp.db.models import FlexibilityCommitment, SuggestionInteraction, UserBadge, UserPoints

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["suggestions"])

BADGES: dict[str, dict] = {
    "first-shift":    {"icon": "zap",         "min_actions": 1},
    "peak-saver":     {"icon": "sun",         "min_actions": 5},
    "solar-champion": {"icon": "leaf",        "min_points": 500},
    "streak-3":       {"icon": "trending-up", "streak_days": 3},
}

POINTS_PER_LEVEL = 100


def _level(points: int) -> int:
    return max(1, points // POINTS_PER_LEVEL + 1)


def _next_level_at(points: int) -> int:
    return _level(points) * POINTS_PER_LEVEL


def _float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _period_from_hour(hour: int) -> str:
    """Map a 24h hour to a suggestion_card.period i18n key."""
    if hour < 5:
        return "night"
    if hour < 8:
        return "early_morning"
    if hour < 11:
        return "morning"
    if hour < 12:
        return "late_morning"
    if hour < 14:
        return "midday"
    if hour < 17:
        return "afternoon"
    if hour < 21:
        return "evening"
    return "night"


# Typical active hours for each period — shown as the "from" clock range.
# "evening" represents the main household appliance window users should shift away from.
_PERIOD_CLOCK: dict[str, str] = {
    "night":         "22:00–06:00",
    "early_morning": "06:00–08:00",
    "morning":       "08:00–10:00",
    "late_morning":  "11:00–12:00",
    "midday":        "12:00–14:00",
    "afternoon":     "14:00–17:00",
    "evening":       "17:00–21:00",
}

# Minimum impact to surface a suggestion (kWh)
_MIN_IMPACT_KWH = 0.5
# Maximum number of suggestions to return
_MAX_SUGGESTIONS = 2


def _shift_from(window_start: datetime, today_date: object) -> tuple[str, str]:
    """Return (from_period, clock_range) for the load to shift AWAY from.

    Tomorrow windows: from=evening (17:00-21:00) → card reads
      "This evening (17:00–21:00) → Tomorrow morning (09:00)"

    Today windows: no "shift from" framing — the window IS the opportunity.
      Return ("", window_clock) so the card shows "Solar surplus 17:00–20:00".
    """
    is_tomorrow = window_start.date() > today_date  # type: ignore[operator]
    if is_tomorrow:
        return "evening", _PERIOD_CLOCK["evening"]
    return "", ""


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
async def suggestions(user: UserDep, db: DbDep, dt: DTDep) -> list[SuggestionItem]:
    """Return tomorrow's top load-shift windows from the rec_flexibility pipeline.

    Only tomorrow's windows are surfaced so every suggestion is always actionable:
    "Move this evening's load (17:00–21:00) to tomorrow morning (09:00–12:00)".
    Results are ordered by estimated impact (kWh) and capped at _MAX_SUGGESTIONS.
    """
    today_dt = datetime.now(timezone.utc).date()

    # Resolve device_id — required to look up per-device flexibility windows
    device_id = ""
    try:
        assets = await dt.participants.assets(user.sub)
        if assets and assets.items:
            for asset in assets.items:
                if asset.sensor_id:
                    device_id = asset.sensor_id
                    break
    except Exception as exc:
        logger.warning("Failed to fetch assets for suggestions: %s", exc)

    if not device_id:
        return []

    # Load suggestion_ids the user has already committed to (status=committed)
    committed_ids: set[str] = set()
    async with db as session:
        rows = (
            await session.execute(
                select(FlexibilityCommitment.suggestion_id).where(
                    FlexibilityCommitment.user_id == user.sub,
                    FlexibilityCommitment.status == "committed",
                )
            )
        ).scalars().all()
        committed_ids = set(rows)

    try:
        res = await dt.participants.fetch_values(
            participant_id=user.sub,
            fetcher_id="rec_flexibility_windows",
            payload={"device_id": device_id},
        )
    except Exception as exc:
        logger.warning("rec_flexibility_windows fetch failed: %s", exc)
        return []

    if not res or res.count == 0:
        return []

    result: list[SuggestionItem] = []
    for item in res.items:
        d: dict[str, Any] = item.to_dict()
        try:
            window_id = str(d.get("_id", ""))
            if window_id in committed_ids:
                continue
            impact = _float(d.get("estimated_kwh"))
            if impact < _MIN_IMPACT_KWH:
                continue
            window_start = datetime.fromisoformat(str(d["window_start"]))
            window_end = datetime.fromisoformat(str(d["window_end"]))
            is_tomorrow = window_start.date() > today_dt
            from_period, from_clock = _shift_from(window_start, today_dt)
            window_clock = f"{window_start.strftime('%H:%M')}–{window_end.strftime('%H:%M')}"
            result.append(
                SuggestionItem(
                    id=str(d.get("_id", "")),
                    suggestion_type="shift-consumption",
                    period_start=window_start.isoformat(),
                    period_end=window_end.isoformat(),
                    from_period=from_period,
                    clock_range=from_clock if from_period else window_clock,
                    to_is_tomorrow=is_tomorrow,
                    to_period=_period_from_hour(window_start.hour),
                    to_time=window_start.strftime("%H:%M"),
                    impact_kwh_estimated=impact,
                    reward_points=int(d.get("reward_points_estimated", 0)),
                    confidence=_float(d.get("confidence"), 0.75),
                )
            )
        except (KeyError, ValueError) as exc:
            logger.warning("Skipping malformed flexibility window: %s", exc)

    # Already ordered by estimated_kwh DESC from the fetcher; cap at max
    return result[:_MAX_SUGGESTIONS]


@router.post(
    "/suggestions/{suggestion_id}/respond", response_model=GamificationResponse
)
async def suggestion_respond(
    suggestion_id: str,
    body: SuggestionRespondRequest,
    user: UserDep,
    db: DbDep,
    dt: DTDep,
) -> GamificationResponse:
    """Record a user's response to a suggestion.

    On acceptance: persists a FlexibilityCommitment preference and publishes a
    flexibility.committed event to the DT (which settles it asynchronously via
    rec_virtual_consumption_per_device).
    """
    now = datetime.now(timezone.utc)

    # Resolve participant context needed for the commitment event
    community_id = ""
    device_id = ""
    try:
        participant = await dt.participants.profile(user.sub)
        _m = participant.membership
        if isinstance(_m, UserMembershipSchema):
            community_id = _m.community.key
    except Exception as exc:
        logger.warning("Failed to fetch participant profile: %s", exc)

    if body.response == "accepted":
        try:
            assets = await dt.participants.assets(user.sub)
            if assets and assets.items:
                for asset in assets.items:
                    if asset.sensor_id:
                        device_id = asset.sensor_id
                        break
        except Exception as exc:
            logger.warning("Failed to fetch assets: %s", exc)

    async with db as session:
        # Get or create points row
        points_row = await session.get(UserPoints, user.sub)
        if points_row is None:
            points_row = UserPoints(user_id=user.sub, total_points=0, level=1)
            session.add(points_row)

        # Upsert interaction
        existing = (
            await session.execute(
                select(SuggestionInteraction).where(
                    SuggestionInteraction.user_id == user.sub,
                    SuggestionInteraction.suggestion_id == suggestion_id,
                )
            )
        ).scalar_one_or_none()

        reward_points = body.reward_points if body.reward_points is not None else 10

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

        # Record commitment preference (BFF-side preference record)
        pending_commitment: FlexibilityCommitment | None = None
        if body.response == "accepted":
            try:
                window_start = datetime.fromisoformat(body.period_start) if body.period_start else now
                window_end = datetime.fromisoformat(body.period_end) if body.period_end else now + timedelta(hours=1)
            except (ValueError, TypeError):
                window_start = now
                window_end = now + timedelta(hours=1)
            pending_commitment = FlexibilityCommitment(
                user_id=user.sub,
                suggestion_id=suggestion_id,
                suggestion_type="shift-consumption",
                period_start=window_start,
                period_end=window_end,
                status="committed",
                reward_points_estimated=reward_points,
            )
            session.add(pending_commitment)

        # Count accepted actions for badge evaluation
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

        await _check_and_award_badges(
            session, user.sub, points_row.total_points, actions_taken
        )
        await session.commit()

        if pending_commitment:
            await session.refresh(pending_commitment)

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
        if pending_commitment:
            commitment_item = FlexibilityCommitmentItem(
                id=str(pending_commitment.id),
                suggestion_id=pending_commitment.suggestion_id,
                status=cast(Literal["committed", "settled", "rejected", "cancelled"], pending_commitment.status),
                period_end=pending_commitment.period_end.isoformat(),
                reward_points_estimated=pending_commitment.reward_points_estimated,
                reward_points_actual=pending_commitment.reward_points_actual,
                committed_at=pending_commitment.committed_at.isoformat(),
                settled_at=pending_commitment.settled_at.isoformat() if pending_commitment.settled_at else None,
            )

    # Publish commitment event to DT (async settlement via rec_it gold tables)
    # Failures are logged but do not fail the response — the preference is already persisted.
    if body.response == "accepted" and pending_commitment and device_id:
        try:
            await dt.participants.flexibility_committed(
                user.sub,
                commitment_id=str(pending_commitment.id),
                community_id=community_id,
                device_id=device_id,
                window_start=window_start,
                window_end=window_end,
                reward_points_estimated=pending_commitment.reward_points_estimated,
            )
        except Exception as exc:
            logger.warning(
                "Failed to publish flexibility_committed event for commitment=%s: %s",
                pending_commitment.id,
                exc,
            )

    return GamificationResponse(
        total_points=points_row.total_points,
        level=points_row.level,
        next_level_at=_next_level_at(points_row.total_points),
        badges=badges,
        actions_taken=actions_taken,
        pending_commitment=commitment_item,
    )


@router.delete("/commitments/{commitment_id}", status_code=204)
async def cancel_commitment(
    commitment_id: str,
    user: UserDep,
    db: DbDep,
) -> None:
    """Cancel a pending flexibility commitment."""
    async with db as session:
        row = (
            await session.execute(
                select(FlexibilityCommitment).where(
                    FlexibilityCommitment.id == commitment_id,
                    FlexibilityCommitment.user_id == user.sub,
                )
            )
        ).scalar_one_or_none()

        if row is None:
            raise HTTPException(status_code=404, detail="Commitment not found")
        if row.status != "committed":
            raise HTTPException(status_code=409, detail="Commitment is not cancellable")

        row.status = "cancelled"
        await session.commit()
