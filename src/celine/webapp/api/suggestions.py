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
    FlexibilityCommitmentItem,
    GamificationResponse,
    SuggestionItem,
    SuggestionRespondRequest,
)
from celine.webapp.db.models import FlexibilityCommitment, SuggestionInteraction, UserBadge, UserPoints

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["suggestions"])

# Threshold: community is net-exporting when net_exchange_kwh > this value (kWh surplus)
EXPORT_THRESHOLD = 0.0
MAX_SUGGESTIONS = 5

BADGES: dict[str, dict] = {
    "first-shift":    {"icon": "zap",         "min_actions": 1},
    "peak-saver":     {"icon": "sun",         "min_actions": 5},
    "solar-champion": {"icon": "leaf",        "min_points": 500},
    "streak-3":       {"icon": "trending-up", "streak_days": 3},
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


def _period_key(start_hour: int) -> str:
    """Return an i18n key for a time-of-day period."""
    if 5 <= start_hour < 9:
        return "early_morning"
    elif 9 <= start_hour < 12:
        return "morning"
    elif 12 <= start_hour < 14:
        return "midday"
    elif 14 <= start_hour < 17:
        return "afternoon"
    elif 17 <= start_hour < 20:
        return "evening"
    else:  # 20-23
        return "night"


def _target_period_key(target_hour: int) -> str:
    """Return an i18n key for the target solar window period."""
    if target_hour < 9:
        return "morning"
    elif target_hour < 12:
        return "late_morning"
    elif target_hour < 14:
        return "midday"
    elif target_hour < 17:
        return "afternoon"
    elif target_hour < 20:
        return "evening"
    else:
        return "night"


def _group_consecutive_hours(
    hours: list[tuple[datetime, float]]
) -> list[list[tuple[datetime, float]]]:
    """Group a chronologically sorted list of (datetime, consumption) into consecutive runs."""
    if not hours:
        return []
    groups: list[list[tuple[datetime, float]]] = [[hours[0]]]
    for dt, kwh in hours[1:]:
        prev_dt = groups[-1][-1][0]
        if (dt - prev_dt) == timedelta(hours=1):
            groups[-1].append((dt, kwh))
        else:
            groups.append([(dt, kwh)])
    return groups


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
async def suggestions(user: UserDep, dt: DTDep) -> list[SuggestionItem]:
    """Generate ranked load-shifting suggestions from today's forecast (05:00–00:00)."""

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

    # Time window: today 05:00 → tomorrow 00:00
    tz = timezone.utc
    today_05 = datetime.now(tz).replace(hour=5, minute=0, second=0, microsecond=0)
    tomorrow_midnight = (today_05 + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    # Fetch REC forecast
    rec_items: list[dict] = []
    try:
        rec_res = await dt.communities.fetch_values(
            community_id=community_id,
            fetcher_id="rec_forecast",
            payload={
                "start": today_05.isoformat(),
                "end": tomorrow_midnight.isoformat(),
            },
        )
        if rec_res and rec_res.count > 0:
            rec_items = [item.to_dict() for item in rec_res.items]
    except Exception as exc:
        logger.warning("rec_forecast fetch failed: %s", exc)

    # Fetch community aggregate meter forecast (total_meters_forecast — no device_id)
    meter_items: list[dict] = []
    try:
        meter_res = await dt.participants.fetch_values(
            participant_id=user.sub,
            fetcher_id="total_meters_forecast",
            payload={
                "start": today_05.isoformat(),
                "end": tomorrow_midnight.isoformat(),
            },
        )
        if meter_res and meter_res.count > 0:
            meter_items = [item.to_dict() for item in meter_res.items]
    except Exception as exc:
        logger.warning("total_meters_forecast fetch failed: %s", exc)

    # Find net-export windows from total_meters_forecast (net_exchange_kwh > 0 = surplus)
    # Do NOT use rec_forecast.prediction for this — it is a community aggregate in Wh,
    # always positive, and not a net-exchange indicator.
    all_surplus_hours: set[str] = set()
    for item in meter_items:
        net_exchange = _float(item.get("net_exchange_kwh"), 0.0)
        if net_exchange > EXPORT_THRESHOLD:
            ts = _str_ts(item.get("timestamp") or item.get("datetime") or "")
            all_surplus_hours.add(ts[:13])

    # Find the best solar target hour (earliest surplus hour, waking hours only)
    target_ts: datetime | None = None
    for item in sorted(meter_items, key=lambda r: _str_ts(r.get("timestamp") or r.get("datetime") or "")):
        net_exchange = _float(item.get("net_exchange_kwh"), 0.0)
        if net_exchange <= EXPORT_THRESHOLD:
            continue
        ts_str = _str_ts(item.get("timestamp") or item.get("datetime") or "")
        try:
            candidate = datetime.fromisoformat(ts_str.replace(" ", "T").split("+")[0])
        except ValueError:
            continue
        if candidate.hour >= 5:
            target_ts = candidate
            break

    if target_ts is None:
        return []

    # Collect non-surplus waking hours sorted chronologically
    import_hours: list[tuple[datetime, float]] = []
    for item in meter_items:
        ts_str = _str_ts(item.get("timestamp") or item.get("datetime") or "")
        hour_key = ts_str[:13]
        if hour_key in all_surplus_hours:
            continue
        try:
            source_dt = datetime.fromisoformat(ts_str.replace(" ", "T").split("+")[0])
        except ValueError:
            continue
        if source_dt.hour < 5:
            continue
        consumption = _float(item.get("consumption_kwh") or item.get("total_consumption_kwh"))
        import_hours.append((source_dt, consumption))

    # Sort chronologically and group consecutive hours
    import_hours.sort(key=lambda x: x[0])
    groups = _group_consecutive_hours(import_hours)

    # Sort groups by total consumption descending, take top MAX_SUGGESTIONS
    groups.sort(key=lambda g: sum(kwh for _, kwh in g), reverse=True)

    result: list[SuggestionItem] = []
    for group in groups[:MAX_SUGGESTIONS]:
        group_start = group[0][0]
        group_end = group[-1][0] + timedelta(hours=1)
        total_consumption = sum(kwh for _, kwh in group)
        impact_kwh = round(total_consumption * 0.6, 2)
        reward_points = round(impact_kwh * 10)

        clock_range = f"{_fmt_label(group_start)}–{_fmt_label(group_end)}"

        result.append(
            SuggestionItem(
                id=_suggestion_id("shift-consumption", group_start.isoformat()[:16]),
                suggestion_type="shift-consumption",
                period_start=group_start.isoformat(),
                period_end=group_end.isoformat(),
                from_period=_period_key(group_start.hour),
                clock_range=clock_range,
                to_is_tomorrow=group_start.hour >= 17,
                to_period=_target_period_key(target_ts.hour),
                to_time=_fmt_label(target_ts),
                impact_kwh_estimated=impact_kwh,
                reward_points=reward_points,
                confidence=0.75,
            )
        )

    return result


@router.post(
    "/suggestions/{suggestion_id}/respond", response_model=GamificationResponse
)
async def suggestion_respond(
    suggestion_id: str,
    body: SuggestionRespondRequest,
    user: UserDep,
    db: DbDep,
) -> GamificationResponse:
    """Record a user's response to a suggestion and update points/badges."""

    now = datetime.now(timezone.utc)

    async with db as session:
        # Lazy-settle any past FlexibilityCommitments where period_end < now
        past_commitments = (
            await session.execute(
                select(FlexibilityCommitment).where(
                    FlexibilityCommitment.user_id == user.sub,
                    FlexibilityCommitment.status == "committed",
                    FlexibilityCommitment.period_end < now,
                )
            )
        ).scalars().all()

        # Get or create points row for settlement
        points_row = await session.get(UserPoints, user.sub)
        if points_row is None:
            points_row = UserPoints(user_id=user.sub, total_points=0, level=1)
            session.add(points_row)

        for commitment in past_commitments:
            # Award estimated points (mock settlement)
            points_row.total_points += commitment.reward_points_estimated
            points_row.level = max(1, points_row.total_points // POINTS_PER_LEVEL + 1)
            points_row.updated_at = now
            commitment.status = "settled"
            commitment.settled_at = now
            commitment.reward_points_actual = commitment.reward_points_estimated

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

        # Create FlexibilityCommitment for accepted responses
        pending_commitment: FlexibilityCommitment | None = None
        if body.response == "accepted":
            pending_commitment = FlexibilityCommitment(
                user_id=user.sub,
                suggestion_id=suggestion_id,
                suggestion_type="shift-consumption",
                period_start=now,
                period_end=now + timedelta(hours=1),
                status="committed",
                reward_points_estimated=reward_points,
            )
            session.add(pending_commitment)

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

        # Refresh pending commitment to get generated fields
        if pending_commitment:
            await session.refresh(pending_commitment)

        # Build response
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
                status=pending_commitment.status,
                period_end=pending_commitment.period_end.isoformat(),
                reward_points_estimated=pending_commitment.reward_points_estimated,
                reward_points_actual=pending_commitment.reward_points_actual,
                committed_at=pending_commitment.committed_at.isoformat(),
                settled_at=pending_commitment.settled_at.isoformat() if pending_commitment.settled_at else None,
            )

    return GamificationResponse(
        total_points=points_row.total_points,
        level=points_row.level,
        next_level_at=_next_level_at(points_row.total_points),
        badges=badges,
        actions_taken=actions_taken,
        pending_commitment=commitment_item,
    )
