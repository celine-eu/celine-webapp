# celine/webapp/api/gamification.py
"""Gamification routes."""
import logging
import math
from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import select, func

from celine.webapp.api.deps import DbDep, DTDep, FlexibilityDep, UserDep
from celine.webapp.api.schemas import (
    BadgeItem,
    CommitmentHistoryResponse,
    DailyPointsItem,
    FlexibilityHistoryItem,
    GamificationResponse,
    RankingInfo,
)
from celine.webapp.db.models import UserBadge, SuggestionInteraction

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

    Points come from rec_participant_points (the pipeline-computed source of
    truth that already includes baseline-validated bonus).  The flexibility-api
    reward_points_actual is NOT used here because the settlement formula does
    not compare against baseline, producing inflated values.
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
        logger.info("gamification: user=%s device_id=%r assets_count=%d", user.sub, device_id, len(assets.items) if assets and assets.items else 0)
    except Exception as exc:
        logger.warning("Asset lookup failed for %s: %s", user.sub, exc)

    # Daily points from rec_participant_points — the pipeline-computed source of
    # truth that includes baseline-validated scoring.
    total_points = 0
    daily_points: list[DailyPointsItem] = []
    if device_id:
        try:
            pts_res = await dt.participants.fetch_values(
                participant_id=user.sub,
                fetcher_id="rec_participant_points",
                payload={"device_id": device_id},
            )
            logger.info(
                "gamification: rec_participant_points user=%s device=%s count=%d",
                user.sub, device_id, pts_res.count if pts_res else 0,
            )
            if pts_res and pts_res.count > 0:
                for item in pts_res.items:
                    d = item.to_dict()
                    logger.debug("gamification: raw row keys=%s values=%s", list(d.keys()), {k: d[k] for k in list(d.keys())[:5]})
                    day = str(d.get("ts_date", ""))
                    pts = int(d.get("daily_points") or 0)
                    total_points += pts
                    daily_points.append(DailyPointsItem(date=day, points=pts))
        except Exception as exc:
            logger.warning("rec_participant_points fetch failed: %s", exc)
    else:
        logger.warning("No device_id found for user %s — daily points unavailable", user.sub)
    daily_points.sort(key=lambda x: x.date)
    logger.info("gamification: user=%s total_points=%d daily_entries=%d", user.sub, total_points, len(daily_points))

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
async def gamification_history(user: UserDep, flexibility: FlexibilityDep, dt: DTDep) -> CommitmentHistoryResponse:
    """Return commitment history with real bonus points from rec_participant_points.

    The flexibility-api settlement computes reward_points_actual from raw
    consumption without baseline comparison, which inflates the value.
    We cross-reference with rec_participant_points (the pipeline source of
    truth) to replace settled reward_points_actual with real earned values.
    """
    try:
        result = await flexibility.list_commitments(limit=50)
    except Exception as exc:
        logger.warning("Failed to fetch commitment history from flexibility-api: %s", exc)
        return CommitmentHistoryResponse(items=[], total_points_earned=0)

    # Fetch real daily points to cross-reference settled bonus values.
    real_daily_points: dict[str, int] = {}
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
                    day = str(d.get("ts_date", ""))
                    real_daily_points[day] = int(d.get("daily_points") or 0)
        except Exception as exc:
            logger.warning("rec_participant_points fetch failed for history: %s", exc)

    items: list[FlexibilityHistoryItem] = []
    total_earned = 0

    for row in result.items:
        actual_pts = row.reward_points_actual

        # For settled commitments, replace the inflated flexibility-api value
        # with the real points from rec_participant_points for that day.
        if row.status.value == "settled" and real_daily_points:
            day = row.period_start.isoformat()[:10]
            actual_pts = real_daily_points.get(day, 0)

        items.append(
            FlexibilityHistoryItem(
                id=str(row.id),
                suggestion_type=row.suggestion_type,
                period_start=row.period_start.isoformat(),
                period_end=row.period_end.isoformat(),
                committed_at=row.committed_at.isoformat(),
                settled_at=row.settled_at.isoformat() if row.settled_at else None,
                status=row.status.value,
                reward_points_estimated=row.reward_points_estimated,
                reward_points_actual=actual_pts,
                impact_kwh_actual=None,
            )
        )
        if actual_pts:
            total_earned += actual_pts

    return CommitmentHistoryResponse(items=items, total_points_earned=total_earned)
