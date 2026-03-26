# celine/webapp/api/gamification.py
"""Gamification routes."""
import hashlib
import logging
import random
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from sqlalchemy import select, func

from celine.webapp.api.deps import DbDep, UserDep
from celine.webapp.api.schemas import (
    BadgeItem,
    CommitmentHistoryResponse,
    FlexibilityHistoryItem,
    GamificationResponse,
    RankingInfo,
)
from celine.webapp.db.models import UserPoints, UserBadge, SuggestionInteraction

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
    return (_level(total_points)) * POINTS_PER_LEVEL


def _user_seed(user_sub: str) -> int:
    """Stable integer seed derived from the user's sub claim."""
    return int(hashlib.md5(user_sub.encode()).hexdigest(), 16) % (2 ** 31)


def _mock_ranking(user_sub: str) -> RankingInfo:
    """Return a mock ranking for the user.

    Produces stable (but fake) results per user_sub. A proper implementation
    will query settlement data from the SDK when available.
    """
    rng = random.Random(_user_seed(user_sub))
    total_members = rng.randint(20, 120)
    position = rng.randint(1, max(1, total_members // 3))
    percentile = max(1, round((position / total_members) * 100))
    period: str = "week"
    return RankingInfo(
        position=position,
        total_members=total_members,
        percentile=percentile,
        period=period,
    )


def _mock_history(user_sub: str) -> CommitmentHistoryResponse:
    """Return mock commitment history for the user.

    Stable per user_sub. A proper implementation will read FlexibilityCommitment
    records via the settlement SDK when available.
    """
    rng = random.Random(_user_seed(user_sub) + 1)
    now = datetime.now(timezone.utc)
    statuses = ["settled", "settled", "settled", "committed", "rejected"]
    types = ["shift-consumption", "delay-load", "avoid-peak"]

    n = rng.randint(3, 6)
    items: list[FlexibilityHistoryItem] = []
    total_earned = 0

    for i in range(n):
        days_ago = rng.randint(1, 28)
        committed_at = now - timedelta(days=days_ago, hours=rng.randint(6, 20))
        period_start = committed_at.replace(minute=0, second=0, microsecond=0)
        period_end = period_start + timedelta(hours=rng.randint(1, 4))
        status = rng.choice(statuses)
        estimated = rng.randint(10, 50)
        actual = (
            round(estimated * rng.uniform(0.8, 1.2))
            if status == "settled"
            else None
        )
        settled_at = (
            (committed_at + timedelta(hours=rng.randint(2, 8))).isoformat()
            if status == "settled"
            else None
        )
        impact = round(rng.uniform(0.3, 3.5), 2) if status == "settled" else None
        if actual:
            total_earned += actual

        items.append(
            FlexibilityHistoryItem(
                id=f"mock-{user_sub[:8]}-{i}",
                suggestion_type=rng.choice(types),
                period_start=period_start.isoformat(),
                period_end=period_end.isoformat(),
                committed_at=committed_at.isoformat(),
                settled_at=settled_at,
                status=status,
                reward_points_estimated=estimated,
                reward_points_actual=actual,
                impact_kwh_actual=impact,
            )
        )

    # Sort newest first
    items.sort(key=lambda x: x.committed_at, reverse=True)
    return CommitmentHistoryResponse(items=items, total_points_earned=total_earned)


@router.get("/gamification", response_model=GamificationResponse)
async def gamification(user: UserDep, db: DbDep) -> GamificationResponse:
    """Return user's total points, level, badges, action count and mock ranking."""

    async with db as session:
        # Points
        points_row = await session.get(UserPoints, user.sub)
        total_points = points_row.total_points if points_row else 0
        level = _level(total_points)

        # Badges
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

        # Actions taken (accepted suggestions)
        actions_taken = (
            await session.execute(
                select(func.count()).where(
                    SuggestionInteraction.user_id == user.sub,
                    SuggestionInteraction.response == "accepted",
                )
            )
        ).scalar() or 0

    return GamificationResponse(
        total_points=total_points,
        level=level,
        next_level_at=_next_level_at(total_points),
        badges=badges,
        actions_taken=actions_taken,
        ranking=_mock_ranking(user.sub),
    )


@router.get("/gamification/history", response_model=CommitmentHistoryResponse)
async def gamification_history(user: UserDep) -> CommitmentHistoryResponse:
    """Return commitment history for the user.

    Currently returns mock data; will be replaced by SDK settlement queries.
    """
    return _mock_history(user.sub)
