# celine/webapp/api/suggestions.py
"""Suggestions routes — GET /api/suggestions, POST /api/suggestions/{id}/respond."""
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, func

from celine.webapp.api.deps import DbDep, DTDep, UserDep
from celine.webapp.api.schemas import (
    BadgeItem,
    GamificationResponse,
    SuggestionItem,
    SuggestionRespondRequest,
)
from celine.webapp.db.models import SuggestionInteraction, UserBadge, UserPoints

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["suggestions"])

# Threshold: community is net-exporting when prediction < this value (kWh/h)
EXPORT_THRESHOLD = 0.0
MAX_SUGGESTIONS = 5

BADGES: dict[str, dict] = {
    "first-shift":    {"label": "First Shift",    "icon": "zap",          "min_actions": 1},
    "peak-saver":     {"label": "Peak Saver",      "icon": "sun",          "min_actions": 5},
    "solar-champion": {"label": "Solar Champion",  "icon": "leaf",         "min_points": 500},
    "streak-3":       {"label": "3-Day Streak",    "icon": "trending-up",  "streak_days": 3},
}

POINTS_PER_LEVEL = 100


def _suggestion_id(suggestion_type: str, period_start: str) -> str:
    raw = f"{suggestion_type}:{period_start}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _str_ts(val: Any) -> str:
    return str(val) if val is not None else ""


def _fmt_label(dt_val: datetime) -> str:
    return dt_val.strftime("%H:%M")


def _level(points: int) -> int:
    return max(1, points // POINTS_PER_LEVEL + 1)


def _next_level_at(points: int) -> int:
    return _level(points) * POINTS_PER_LEVEL


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
            await session.execute(
                select(UserBadge).where(UserBadge.user_id == user_id)
            )
        ).scalars().all()
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
async def suggestions(user: UserDep, dt: DTDep) -> list[SuggestionItem]:
    """Generate ranked load-shifting suggestions from the 48h forecast."""

    participant = await dt.participants.profile(user.sub)
    community_id = participant.membership.community.key

    device_id: str | None = None
    try:
        assets = await dt.participants.assets(user.sub)
        if assets and assets.items:
            for asset in assets.items:
                if asset.sensor_id:
                    device_id = asset.sensor_id
                    break
    except Exception as exc:
        logger.warning("Failed to fetch assets: %s", exc)

    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=48)

    # Fetch REC forecast
    rec_items: list[dict] = []
    try:
        rec_res = await dt.communities.fetch_values(
            community_id=community_id,
            fetcher_id="rec_forecast",
            payload={"start": now.isoformat(), "end": end.isoformat()},
        )
        if rec_res and rec_res.count > 0:
            rec_items = [item.to_dict() for item in rec_res.items]
    except Exception as exc:
        logger.warning("rec_forecast fetch failed: %s", exc)

    # Fetch user meter forecast
    meter_items: list[dict] = []
    if device_id:
        try:
            meter_res = await dt.participants.fetch_values(
                participant_id=user.sub,
                fetcher_id="meter_forecast",
                payload={
                    "device_id": device_id,
                    "start": now.isoformat(),
                    "end": end.isoformat(),
                },
            )
            if meter_res and meter_res.count > 0:
                meter_items = [item.to_dict() for item in meter_res.items]
        except Exception as exc:
            logger.warning("meter_forecast fetch failed: %s", exc)

    # Find net-export windows (community exporting = excess solar available)
    export_hours: set[str] = set()
    for item in rec_items:
        prediction = _float(item.get("prediction"), 999.0)
        if prediction < EXPORT_THRESHOLD:
            ts = _str_ts(item.get("datetime") or item.get("ts"))
            export_hours.add(ts[:13])  # group by hour prefix YYYY-MM-DDTHH

    # Find user's high-consumption hours outside solar windows
    result: list[SuggestionItem] = []
    seen_windows: set[str] = set()

    # Sort meter items by consumption descending
    meter_items_sorted = sorted(
        meter_items,
        key=lambda r: _float(r.get("total_consumption_kwh")),
        reverse=True,
    )

    for item in meter_items_sorted:
        if len(result) >= MAX_SUGGESTIONS:
            break

        ts = item.get("timestamp") or item.get("datetime") or ""
        ts_str = _str_ts(ts)
        hour_key = ts_str[:13]

        # Skip if this is already a solar surplus hour (no shift needed)
        if hour_key in export_hours:
            continue

        # Find best target hour in solar window
        target_ts: datetime | None = None
        for rec_item in rec_items:
            rec_ts = _str_ts(rec_item.get("datetime") or rec_item.get("ts"))
            if rec_ts[:13] in export_hours:
                try:
                    target_ts = datetime.fromisoformat(
                        rec_ts.replace(" ", "T").split("+")[0]
                    )
                except ValueError:
                    continue
                break

        if target_ts is None:
            continue

        try:
            source_dt = datetime.fromisoformat(ts_str.replace(" ", "T").split("+")[0])
        except ValueError:
            continue

        window_key = f"{ts_str[:13]}->{target_ts.isoformat()[:13]}"
        if window_key in seen_windows:
            continue
        seen_windows.add(window_key)

        consumption = _float(item.get("total_consumption_kwh"))
        impact_kwh = round(consumption * 0.6, 2)  # assume 60% shiftable
        reward_points = round(impact_kwh * 10)
        period_end_dt = source_dt + timedelta(hours=1)
        target_end_dt = target_ts + timedelta(hours=1)

        result.append(
            SuggestionItem(
                id=_suggestion_id("shift-consumption", ts_str[:16]),
                suggestion_type="shift-consumption",
                period_start=source_dt.isoformat(),
                period_end=period_end_dt.isoformat(),
                from_label=f"{_fmt_label(source_dt)}–{_fmt_label(period_end_dt)}",
                to_label=f"{_fmt_label(target_ts)}–{_fmt_label(target_end_dt)}",
                impact_kwh_estimated=impact_kwh,
                reward_points=reward_points,
                confidence=0.75,
                description=f"Shift loads from {_fmt_label(source_dt)} to {_fmt_label(target_ts)} when solar is available",
                reason="Community will have excess solar — reduce grid import and earn points",
            )
        )

    return result


@router.post("/suggestions/{suggestion_id}/respond", response_model=GamificationResponse)
async def suggestion_respond(
    suggestion_id: str,
    body: SuggestionRespondRequest,
    user: UserDep,
    db: DbDep,
) -> GamificationResponse:
    """Record a user's response to a suggestion and update points/badges."""

    now = datetime.now(timezone.utc)

    async with db as session:
        # Upsert interaction
        existing = (
            await session.execute(
                select(SuggestionInteraction).where(
                    SuggestionInteraction.user_id == user.sub,
                    SuggestionInteraction.suggestion_id == suggestion_id,
                )
            )
        ).scalar_one_or_none()

        reward_points = 0
        if body.response == "accepted":
            # Simple point estimate — real value comes from the suggestion payload
            reward_points = 10

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

        # Update points
        points_row = await session.get(UserPoints, user.sub)
        if points_row is None:
            points_row = UserPoints(user_id=user.sub, total_points=0, level=1)
            session.add(points_row)

        if body.response == "accepted":
            points_row.total_points += reward_points
            points_row.level = max(1, points_row.total_points // POINTS_PER_LEVEL + 1)
            points_row.updated_at = now

        # Count accepted actions
        actions_taken = (
            await session.execute(
                select(func.count()).where(
                    SuggestionInteraction.user_id == user.sub,
                    SuggestionInteraction.response == "accepted",
                )
            )
        ).scalar() or 0

        # Add current action if newly accepted
        if body.response == "accepted" and not existing:
            actions_taken += 1

        await _check_and_award_badges(
            session, user.sub, points_row.total_points, actions_taken
        )
        await session.commit()

        # Build response
        badge_rows = (
            await session.execute(
                select(UserBadge).where(UserBadge.user_id == user.sub)
            )
        ).scalars().all()

        badges = [
            BadgeItem(
                badge_id=b.badge_id,
                label=BADGES.get(b.badge_id, {}).get("label", b.badge_id),
                icon=BADGES.get(b.badge_id, {}).get("icon", "award"),
                earned_at=b.earned_at.isoformat(),
            )
            for b in badge_rows
        ]

    return GamificationResponse(
        total_points=points_row.total_points,
        level=points_row.level,
        next_level_at=_next_level_at(points_row.total_points),
        badges=badges,
        actions_taken=actions_taken,
    )
