# celine/webapp/api/gamification.py
"""Gamification route — GET /api/gamification."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import select, func

from celine.webapp.api.deps import DbDep, UserDep
from celine.webapp.api.schemas import BadgeItem, GamificationResponse
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


@router.get("/gamification", response_model=GamificationResponse)
async def gamification(user: UserDep, db: DbDep) -> GamificationResponse:
    """Return user's total points, level, badges, and action count."""

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
    )
