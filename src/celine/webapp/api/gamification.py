# celine/webapp/api/gamification.py
"""Gamification routes."""
import logging
import math
from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import select, func

from celine.webapp.api.deps import DbDep, DTDep, UserDep
from celine.webapp.api.schemas import (
    BadgeItem,
    CommitmentHistoryResponse,
    DailyPointsItem,
    FlexibilityHistoryItem,
    GamificationResponse,
    RankingInfo,
)
from celine.webapp.db.models import FlexibilityCommitment, UserBadge, SuggestionInteraction

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["gamification"])

BADGES: dict[str, dict] = {
    "first-shift":    {"icon": "zap",         "min_actions": 1},
    "peak-saver":     {"icon": "sun",         "min_actions": 5},
    "solar-champion": {"icon": "leaf",        "min_points": 500},
    "streak-3":       {"icon": "trending-up", "streak_days": 3},
}

POINTS_PER_LEVEL = 100


def _level(total_points: int) -> int:
    return max(1, total_points // POINTS_PER_LEVEL + 1)


def _next_level_at(total_points: int) -> int:
    return _level(total_points) * POINTS_PER_LEVEL


@router.get("/gamification", response_model=GamificationResponse)
async def gamification(user: UserDep, db: DbDep, dt: DTDep) -> GamificationResponse:
    """Return user's total points, level, badges, action count and real ranking.

    Total points are derived from rec_participant_points (dbt gold table) which
    sums ALL virtual self-consumption — base loads and flexibility windows alike.
    """
    async with db as session:
        badge_rows = (
            await session.execute(
                select(UserBadge).where(UserBadge.user_id == user.sub)
            )
        ).scalars().all()

        badges = [
            BadgeItem(
                badge_id=b.badge_id,
                icon=BADGES.get(b.badge_id, {}).get("icon", "zap"),
                earned_at=b.earned_at.isoformat(),
            )
            for b in badge_rows
        ]

        actions_taken = (
            await session.execute(
                select(func.count()).where(
                    SuggestionInteraction.user_id == user.sub,
                    SuggestionInteraction.response == "accepted",
                )
            )
        ).scalar() or 0

    # Resolve participant's device_id once; used for both points and ranking.
    device_id = ""
    try:
        assets = await dt.participants.assets(user.sub)
        if assets and assets.items:
            for asset in assets.items:
                if asset.sensor_id:
                    device_id = asset.sensor_id
                    break
    except Exception as exc:
        logger.warning("Asset lookup failed for %s: %s", user.sub, exc)

    # Total points + daily breakdown from rec_participant_points.
    # Covers ALL virtual self-consumption (base loads + flexibility windows).
    total_points = 0
    daily_points: list[DailyPointsItem] = []
    if device_id:
        try:
            pts_res = await dt.participants.fetch_values(
                participant_id=user.sub,
                fetcher_id="rec_participant_points",
                payload={"device_id": device_id},
            )
            if pts_res and pts_res.count > 0:
                for item in pts_res.items:
                    d = item.to_dict()
                    pts = int(d.get("daily_points") or 0)
                    total_points += pts
                    daily_points.append(
                        DailyPointsItem(date=str(d.get("ts_date", "")), points=pts)
                    )
        except Exception as exc:
            logger.warning("rec_participant_points fetch failed: %s", exc)

    # Community ranking from rec_gamification_summary (today's snapshot).
    ranking: RankingInfo | None = None
    if device_id:
        try:
            today = datetime.now(timezone.utc).date().isoformat()
            res = await dt.participants.fetch_values(
                participant_id=user.sub,
                fetcher_id="rec_gamification_summary",
                payload={"device_id": device_id, "date": today},
            )
            if res and res.count > 0:
                d = res.items[0].to_dict()
                position = int(d.get("rank_position", 1))
                total = max(int(d.get("total_members", 1)), 1)
                top_pct = math.ceil(position / total * 100)
                ranking = RankingInfo(
                    position=position,
                    total_members=total,
                    percentile=top_pct,
                    period="day",
                )
        except Exception as exc:
            logger.warning("rec_gamification_summary fetch failed: %s", exc)

    return GamificationResponse(
        total_points=total_points,
        level=_level(total_points),
        next_level_at=_next_level_at(total_points),
        badges=badges,
        actions_taken=actions_taken,
        ranking=ranking,
        daily_points=daily_points,
    )


@router.get("/gamification/history", response_model=CommitmentHistoryResponse)
async def gamification_history(user: UserDep, db: DbDep) -> CommitmentHistoryResponse:
    """Return commitment history from BFF DB (settled asynchronously by flexibility-api)."""

    async with db as session:
        rows = (
            await session.execute(
                select(FlexibilityCommitment)
                .where(FlexibilityCommitment.user_id == user.sub)
                .order_by(FlexibilityCommitment.committed_at.desc())
                .limit(50)
            )
        ).scalars().all()

    items: list[FlexibilityHistoryItem] = []
    total_earned = 0

    for row in rows:
        items.append(
            FlexibilityHistoryItem(
                id=str(row.id),
                suggestion_type=row.suggestion_type,
                period_start=row.period_start.isoformat(),
                period_end=row.period_end.isoformat(),
                committed_at=row.committed_at.isoformat(),
                settled_at=row.settled_at.isoformat() if row.settled_at else None,
                status=row.status,
                reward_points_estimated=row.reward_points_estimated,
                reward_points_actual=row.reward_points_actual,
                impact_kwh_actual=None,
            )
        )
        if row.reward_points_actual:
            total_earned += row.reward_points_actual

    return CommitmentHistoryResponse(items=items, total_points_earned=total_earned)
