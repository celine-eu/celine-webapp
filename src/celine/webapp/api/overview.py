# celine/webapp/api/overview.py
"""Overview and dashboard routes."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from celine.sdk.dt.community import DTApiError
from celine.sdk.openapi.dt.types import Unset, UNSET

from fastapi import APIRouter, HTTPException

from celine.webapp.api.deps import DbDep, DTDep, UserDep, ensure_user_exists
from celine.webapp.api.schemas import OverviewResponse


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["overview"])


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _compute_self_consumption_rate(
    self_consumption: float | None,
    consumption: float | None,
) -> float | None:
    """Compute self-consumption rate, handling edge cases."""
    if self_consumption is None or consumption is None:
        return None
    if consumption <= 0:
        return 0.0
    return self_consumption / consumption


@router.get("/overview", response_model=OverviewResponse)
async def overview(
    user: UserDep,
    db: DbDep,
    dt: DTDep,
) -> OverviewResponse:
    """Get overview dashboard data from the Digital Twin.

    Fetches:
    - User's meter data from participant domain (meters_data value fetcher)
    - REC-level self-consumption from community domain (rec_self_consumption value fetcher)
    """
    db_user = await ensure_user_exists(user, db)

    # Resolve participant's community.
    participant_id = user.sub
    community_id: str | None = None
    device_id: str | None = None

    participant = await dt.participants.profile(participant_id)

    if participant.membership is None or isinstance(participant.membership, Unset):
        raise HTTPException(404, "User has no membership")

    if participant.membership.member is None or isinstance(
        participant.membership.member, Unset
    ):
        raise HTTPException(404, "User has no membership")

    community_id = participant.membership.community.key
    member_id = participant.membership.member.key

    # Get device_id from participant's delivery points or assets
    # This assumes the member has meter information in their profile
    delivery_points = getattr(participant.membership.member, "delivery_points", None)
    if delivery_points and len(delivery_points) > 0:
        device_id = delivery_points[0].meter_id  # or appropriate field

    # Initialize response data
    user_data: dict = {
        "production_kwh": None,
        "consumption_kwh": None,
        "self_consumption_kwh": None,
        "self_consumption_rate": None,
    }
    rec_data: dict = {
        "production_kwh": None,
        "consumption_kwh": None,
        "self_consumption_kwh": None,
        "self_consumption_rate": None,
    }
    trend: list[dict] = []

    # Time range for queries (last 12 hours for user data, last 7 days for trend)
    now = datetime.now(timezone.utc)
    twelve_hours_ago = now - timedelta(hours=12)
    seven_days_ago = now - timedelta(days=7)

    # -------------------------------------------------------------------------
    # Fetch user meter data (last 12 hours) using the meters_data value fetcher
    # -------------------------------------------------------------------------
    if device_id:
        try:
            # POST /participants/{participant_id}/values/meters_data
            meters_response = await dt.participants.fetch_values(
                participant_id=participant_id,
                fetcher_id="meters_data",
                payload={
                    "device_id": device_id,
                    "start": twelve_hours_ago.isoformat(),
                    "end": now.isoformat(),
                },
            )

            # Aggregate meter readings
            items = meters_response.items
            if items:
                total_consumption = sum(
                    _safe_float(r.to_dict().get("consumption_kw")) for r in items
                )
                total_production = sum(
                    _safe_float(r.to_dict().get("production_kw")) for r in items
                )
                total_self_consumed = sum(
                    _safe_float(r.to_dict().get("self_consumed_kw")) for r in items
                )

                # Convert from kW readings (15-min intervals) to kWh
                # Each reading is 15 minutes = 0.25 hours
                interval_hours = 0.25
                user_data = {
                    "production_kwh": total_production * interval_hours,
                    "consumption_kwh": total_consumption * interval_hours,
                    "self_consumption_kwh": total_self_consumed * interval_hours,
                    "self_consumption_rate": _compute_self_consumption_rate(
                        total_self_consumed * interval_hours,
                        total_consumption * interval_hours,
                    ),
                }

        except DTApiError as exc:
            logger.warning(
                "Failed to fetch meter data for participant %s (device %s): %s",
                participant_id,
                device_id,
                exc,
            )

    # -------------------------------------------------------------------------
    # Fetch REC-level self-consumption using rec_self_consumption value fetcher
    # -------------------------------------------------------------------------
    if community_id:
        try:
            # POST /communities/it/{community_id}/values/rec_self_consumption
            rec_response = await dt.communities.fetch_values(
                community_id=community_id,
                fetcher_id="rec_self_consumption",
                payload={
                    "start": seven_days_ago.isoformat(),
                    "end": now.isoformat(),
                },
            )

            # Aggregate REC data
            items = rec_response.items
            if items:
                # Sum up hourly values
                total_rec_consumption = sum(
                    _safe_float(r.to_dict().get("total_consumption_kw")) for r in items
                )
                total_rec_production = sum(
                    _safe_float(r.to_dict().get("total_production_kw")) for r in items
                )
                total_rec_self_consumption = sum(
                    _safe_float(r.to_dict().get("self_consumption_kw")) for r in items
                )

                rec_data = {
                    "production_kwh": total_rec_production,  # Already in kWh (hourly)
                    "consumption_kwh": total_rec_consumption,
                    "self_consumption_kwh": total_rec_self_consumption,
                    "self_consumption_rate": _compute_self_consumption_rate(
                        total_rec_self_consumption,
                        total_rec_consumption,
                    ),
                }

                # Build trend from the same data (group by day)
                trend = _build_daily_trend(
                    [item.to_dict() for item in items], seven_days_ago, now
                )

        except DTApiError as exc:
            logger.warning(
                "Failed to fetch REC self-consumption for community %s: %s",
                community_id,
                exc,
            )

    # Fallback trend if DT didn't provide data
    if not trend:
        base = datetime.now(timezone.utc).date()
        for d in range(7):
            day = (base - timedelta(days=(6 - d))).isoformat()
            trend.append(
                {
                    "date": day,
                    "production_kwh": None,
                    "consumption_kwh": None,
                    "self_consumption_kwh": None,
                }
            )

    return OverviewResponse(
        period="Last 7 days",
        user=user_data,
        rec=rec_data,
        trend=trend,
    )


def _build_daily_trend(
    items: list[dict],
    start: datetime,
    end: datetime,
) -> list[dict]:
    """Build daily trend from hourly REC data.

    Groups hourly rec_virtual_consumption records by day and sums values.
    """
    from collections import defaultdict

    daily_data: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "production_kwh": 0.0,
            "consumption_kwh": 0.0,
            "self_consumption_kwh": 0.0,
        }
    )

    for item in items:
        ts_str = item.get("ts")
        if not ts_str:
            continue

        # Parse timestamp and extract date
        try:
            if isinstance(ts_str, str):
                # Handle various timestamp formats
                ts = datetime.fromisoformat(ts_str.replace(" ", "T").split("+")[0])
            else:
                ts = ts_str
            date_key = ts.date().isoformat()
        except (ValueError, AttributeError):
            continue

        daily_data[date_key]["consumption_kwh"] += _safe_float(
            item.get("total_consumption_kw")
        )
        daily_data[date_key]["production_kwh"] += _safe_float(
            item.get("total_production_kw")
        )
        daily_data[date_key]["self_consumption_kwh"] += _safe_float(
            item.get("self_consumption_kw")
        )

    # Build sorted trend list for last 7 days
    trend = []
    base = end.date()
    for d in range(7):
        day = (base - timedelta(days=(6 - d))).isoformat()
        if day in daily_data:
            trend.append(
                {
                    "date": day,
                    **daily_data[day],
                }
            )
        else:
            trend.append(
                {
                    "date": day,
                    "production_kwh": None,
                    "consumption_kwh": None,
                    "self_consumption_kwh": None,
                }
            )

    return trend
