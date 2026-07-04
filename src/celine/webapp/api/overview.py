# celine/webapp/api/overview.py
"""Overview and dashboard routes."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from celine.sdk.dt.community import DTApiError
from celine.sdk.openapi.dt import errors as dt_errors
from celine.sdk.openapi.dt.types import Unset, UNSET

from fastapi import APIRouter, HTTPException, Query

from celine.webapp.api.deps import DbDep, DTDep, UserDep
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
    days: int = Query(7, ge=7, le=30, description="Number of days to include in the trend (7 or 30)"),
) -> OverviewResponse:
    """Get overview dashboard data from the Digital Twin.

    Fetches:
    - User's meter data from participant domain (meters_data value fetcher)
    - REC-level self-consumption from community domain (rec_self_consumption value fetcher)
    """

    # Resolve participant's community.
    participant_id = user.sub
    community_id: str | None = None
    device_ids: list[str] = []

    try:
        participant = await dt.participants.profile(participant_id)
    except DTApiError as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail="not_a_participant")
        raise
    except dt_errors.UnexpectedStatus as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail="not_a_participant")
        raise

    if participant.membership is None or isinstance(participant.membership, Unset):
        raise HTTPException(404, "User has no membership")

    if participant.membership.member is None or isinstance(
        participant.membership.member, Unset
    ):
        raise HTTPException(404, "User has no membership")

    community_id = participant.membership.community.key
    member_id = participant.membership.member.key

    devices: list[dict] = []
    try:
        assets = await dt.participants.assets(participant_id)
        if assets:
            for asset in assets.items:
                if asset.sensor_id:
                    devices.append(
                        {
                            "sensor_id": asset.sensor_id,
                            "key": asset.key,
                            "name": asset.name,
                            "details": asset.device.to_dict() if asset.device else {},
                        }
                    )
                    device_ids.append(asset.sensor_id)
        # Get device_id from participant's delivery points or assets
        # This assumes the member has meter information in their profile
        delivery_points = getattr(
            participant.membership.member, "delivery_points", None
        )
        if delivery_points and len(delivery_points) > 0:
            device_ids = delivery_points[0].meter_id  # or appropriate field
    except Exception as ex:
        logger.warning(f"Failed to fetch devices for {user.sub}")

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

    # Time range for queries
    now = datetime.now(timezone.utc)
    trend_start = now - timedelta(days=days)

    # -------------------------------------------------------------------------
    # Fetch user meter data over the selected period (7 or 30 days) using the
    # meters_data value fetcher, so "Your contribution" matches the day toggle
    # and the community totals column (previously this used a fixed 12h window).
    # -------------------------------------------------------------------------
    meters_items_raw: list[dict] = []
    if len(device_ids) > 0:
        try:
            device_id = device_ids[0]

            # POST /participants/{participant_id}/values/meters_data
            meters_response = await dt.participants.fetch_values(
                participant_id=participant_id,
                fetcher_id="meters_data",
                payload={
                    "device_id": device_id,
                    "start": trend_start.isoformat(),
                    "end": now.isoformat(),
                },
            )

            # Aggregate meter readings and retain raw items for trend building
            items = meters_response.items
            if items:
                meters_items_raw = [r.to_dict() for r in items]
                total_consumption = sum(
                    _safe_float(r.get("consumption_kw")) for r in meters_items_raw
                )
                total_production = sum(
                    _safe_float(r.get("production_kw")) for r in meters_items_raw
                )

                production_kwh = total_production
                consumption_kwh = total_consumption
                user_data = {
                    "production_kwh": production_kwh,
                    "consumption_kwh": consumption_kwh,
                    "self_consumption_kwh": None,
                    "self_consumption_rate": None,
                }

        except Exception as exc:
            logger.warning(
                "Failed to fetch meter data for participant %s (device %s): %s",
                participant_id,
                device_ids,
                exc,
            )

    # -------------------------------------------------------------------------
    # Fetch per-device virtual consumption for shared energy allocation
    # -------------------------------------------------------------------------
    user_trend: list[dict] = []
    virtual_items_raw: list[dict] = []
    if len(device_ids) > 0:
        try:
            device_id = device_ids[0]
            user_trend_response = await dt.participants.fetch_values(
                participant_id=participant_id,
                fetcher_id="rec_virtual_consumption_per_device_15m",
                payload={
                    "device_id": device_id,
                    "start": trend_start.isoformat(),
                    "end": now.isoformat(),
                },
            )
            if user_trend_response and user_trend_response.count > 0:
                virtual_items_raw = [item.to_dict() for item in user_trend_response.items]
                shared_kwh = sum(
                    _safe_float(item.get("virtual_consumption_kwh"))
                    for item in virtual_items_raw
                )
                user_data["self_consumption_kwh"] = shared_kwh
                user_data["self_consumption_rate"] = _compute_self_consumption_rate(
                    shared_kwh,
                    user_data.get("consumption_kwh"),
                )
        except Exception as exc:
            logger.warning(
                "Failed to fetch user trend for participant %s: %s",
                participant_id,
                exc,
            )

    # Build user daily trend from meters_data (import/export) + virtual consumption (shared energy)
    if meters_items_raw or virtual_items_raw:
        user_trend = _build_user_daily_trend_merged(
            meters_items_raw, virtual_items_raw, trend_start, now,
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
                    "start": trend_start.isoformat(),
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
                    [item.to_dict() for item in items], trend_start, now
                )

        except Exception as exc:
            logger.warning(
                "Failed to fetch REC self-consumption for community %s: %s",
                community_id,
                exc,
            )

    # Fallback trend if DT didn't provide data
    if not trend:
        base = datetime.now(timezone.utc).date()
        for d in range(days):
            day = (base - timedelta(days=(days - 1 - d))).isoformat()
            trend.append(
                {
                    "date": day,
                    "production_kwh": None,
                    "consumption_kwh": None,
                    "self_consumption_kwh": None,
                    "surplus_kwh": None,
                }
            )

    return OverviewResponse(
        period=f"Last {days} days",
        user=user_data,
        rec=rec_data,
        trend=trend,
        user_trend=user_trend,
        devices=devices,
    )


def _parse_date_key(ts_str: Any) -> str | None:
    """Extract YYYY-MM-DD date key from a timestamp string or datetime."""
    if not ts_str:
        return None
    try:
        if isinstance(ts_str, str):
            ts = datetime.fromisoformat(ts_str.replace(" ", "T").split("+")[0])
        else:
            ts = ts_str
        return ts.date().isoformat()
    except (ValueError, AttributeError):
        return None


def _build_user_daily_trend_merged(
    meter_items: list[dict],
    virtual_items: list[dict],
    start: datetime,
    end: datetime,
) -> list[dict]:
    """Build daily user trend from meters_data (import/export) and virtual consumption (shared energy)."""
    from collections import defaultdict

    num_days = max(1, (end.date() - start.date()).days + 1)

    meter_daily: dict[str, dict[str, float]] = defaultdict(
        lambda: {"consumption_kwh": 0.0, "production_kwh": 0.0}
    )
    for item in meter_items:
        date_key = _parse_date_key(item.get("ts"))
        if not date_key:
            continue
        meter_daily[date_key]["consumption_kwh"] += _safe_float(item.get("consumption_kw"))
        meter_daily[date_key]["production_kwh"] += _safe_float(item.get("production_kw"))

    virtual_daily: dict[str, float] = defaultdict(float)
    for item in virtual_items:
        date_key = _parse_date_key(item.get("ts"))
        if not date_key:
            continue
        virtual_daily[date_key] += _safe_float(item.get("virtual_consumption_kwh"))

    trend = []
    base = end.date()
    for d in range(num_days):
        day = (base - timedelta(days=(num_days - 1 - d))).isoformat()
        has_meter = day in meter_daily
        has_virtual = day in virtual_daily
        if has_meter or has_virtual:
            trend.append({
                "date": day,
                "consumption_kwh": meter_daily[day]["consumption_kwh"] if has_meter else None,
                "production_kwh": meter_daily[day]["production_kwh"] if has_meter else None,
                "self_consumption_kwh": virtual_daily[day] if has_virtual else None,
            })
        else:
            trend.append({
                "date": day,
                "consumption_kwh": None,
                "production_kwh": None,
                "self_consumption_kwh": None,
            })

    return trend


def _build_daily_trend(
    items: list[dict],
    start: datetime,
    end: datetime,
) -> list[dict]:
    """Build daily trend from hourly REC data.

    Groups hourly rec_virtual_consumption records by day and sums values.
    """
    from collections import defaultdict

    num_days = max(1, (end.date() - start.date()).days + 1)

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

    # Build sorted trend list for the requested period
    trend = []
    base = end.date()
    for d in range(num_days):
        day = (base - timedelta(days=(num_days - 1 - d))).isoformat()
        if day in daily_data:
            dd = daily_data[day]
            surplus = max(0.0, dd["production_kwh"] - dd["consumption_kwh"])
            trend.append({
                "date": day,
                **dd,
                "surplus_kwh": surplus,
            })
        else:
            trend.append({
                "date": day,
                "production_kwh": None,
                "consumption_kwh": None,
                "self_consumption_kwh": None,
                "surplus_kwh": None,
            })

    return trend
