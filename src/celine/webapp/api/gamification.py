# celine/webapp/api/gamification.py
"""Gamification routes."""
import logging
import math

from fastapi import APIRouter
from pydantic import BaseModel
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


class SeasonSummary(BaseModel):
    """Season-scoped totals + anonymous rank mapped from a rec_points_leaderboard row."""

    total_points: int
    season_base_points: int
    season_bonus_points: int
    season_start: str
    season_end: str
    ranking: RankingInfo


def _season_summary_from_row(row: dict) -> SeasonSummary | None:
    """Map a rec_points_leaderboard row to a SeasonSummary.

    Args:
        row: Row dict from the rec_points_leaderboard DT fetcher.

    Returns:
        The mapped summary, or None when the row is missing/malformed so the
        caller can fall back to the legacy all-time behavior.
    """
    try:
        position = int(row["season_rank"])
        total = max(int(row["total_members"]), 1)
        return SeasonSummary(
            total_points=int(row["season_points"]),
            season_base_points=int(row["season_base_points"]),
            season_bonus_points=int(row["season_bonus_points"]),
            season_start=str(row["season_start"]),
            season_end=str(row["season_end"]),
            ranking=RankingInfo(
                position=position,
                total_members=total,
                percentile=math.ceil(position / total * 100),
                period="season",
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("rec_points_leaderboard row unusable, falling back: %s", exc)
        return None


async def _fetch_leaderboard_row(dt, participant_id: str, device_id: str) -> dict | None:
    """Fetch the participant's current-season rec_points_leaderboard row.

    Returns None on any failure or empty result (old DT deployed, device not in
    the fleet, brand-new device before the first pipeline run) — the caller then
    falls back to summing rec_participant_points.
    """
    try:
        res = await dt.participants.fetch_values(
            participant_id=participant_id,
            fetcher_id="rec_points_leaderboard",
            payload={"device_id": device_id},
        )
    except Exception as exc:
        logger.warning("rec_points_leaderboard fetch failed (fallback to all-time sum): %s", exc)
        return None
    if res and res.count > 0:
        return res.items[0].to_dict()
    return None


@router.get("/gamification", response_model=GamificationResponse)
async def gamification(user: UserDep, db: DbDep, dt: DTDep) -> GamificationResponse:
    """Return user's season points, level, badges, action count and anonymous rank.

    Headline total_points, level and next_level_at are scoped to the current
    season (from rec_points_leaderboard), so the level ladder resets each season
    (POINTS_PER_LEVEL = 100, applied to season points). Ranking is the
    participant's own anonymous season rank (period="season").

    When the season leaderboard row is unavailable or malformed (old DT
    deployed, device not in the fleet, brand-new device), the endpoint falls
    back to the legacy all-time behavior: total_points = sum of
    rec_participant_points daily points and ranking = None. Points come from
    rec_participant_points (the pipeline-computed source of truth that already
    includes baseline-validated bonus). The flexibility-api reward_points_actual
    is NOT used here because the settlement formula does not compare against
    baseline, producing inflated values.
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

    # Season totals + anonymous rank from rec_points_leaderboard (one current-season row).
    season: SeasonSummary | None = None
    if device_id:
        row = await _fetch_leaderboard_row(dt, user.sub, device_id)
        if row is not None:
            season = _season_summary_from_row(row)

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

    if season is not None:
        total_points = season.total_points

    logger.info("gamification: user=%s total_points=%d daily_entries=%d", user.sub, total_points, len(daily_points))

    # Ranking comes exclusively from the season leaderboard (anonymous rank, own row
    # only). The daily rec_gamification_summary fetcher is no longer called here —
    # in fallback mode the panel simply shows no ranking.
    ranking: RankingInfo | None = season.ranking if season is not None else None

    return GamificationResponse(
        total_points=total_points,
        level=_level(total_points),
        next_level_at=_next_level_at(total_points),
        badges=badges,
        actions_taken=actions_taken,
        ranking=ranking,
        daily_points=daily_points,
        season_start=season.season_start if season is not None else None,
        season_end=season.season_end if season is not None else None,
        season_base_points=season.season_base_points if season is not None else None,
        season_bonus_points=season.season_bonus_points if season is not None else None,
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
