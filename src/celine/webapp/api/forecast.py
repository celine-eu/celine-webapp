# celine/webapp/api/forecast.py
"""Forecast route — GET /api/forecast."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Query

from celine.webapp.api.deps import DTDep, UserDep
from celine.webapp.api.schemas import ForecastHourItem, ForecastResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["forecast"])


def _float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _first_value(row: dict[str, Any], *keys: str) -> float | None:
    """Return the first non-null value among ``keys``, as float.

    The meter forecast pipeline moved from ``total_*`` to ``grid_*`` columns;
    dataset-api's SQL allowlist blocks COALESCE, so the fallback happens here.
    """
    for key in keys:
        value = row.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def _str(val: Any) -> str:
    return str(val) if val is not None else ""


def _parse_ts(ts: str) -> datetime:
    """Parse an ISO timestamp for ordering; naive values are assumed UTC."""
    try:
        parsed = datetime.fromisoformat(ts)
    except ValueError:
        return datetime.max.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _sort_dedup(items: list[ForecastHourItem]) -> list[ForecastHourItem]:
    """Order by timestamp and keep one row per instant.

    The upstream fetchers already deduplicate forecast runs; this guards the
    chart against regressions (duplicate timestamps render as a sawtooth).
    """
    deduped: dict[datetime, ForecastHourItem] = {}
    for item in items:
        deduped.setdefault(_parse_ts(item.ts), item)
    return [deduped[key] for key in sorted(deduped)]


@router.get("/forecast", response_model=ForecastResponse)
async def forecast(
    user: UserDep,
    dt: DTDep,
    days: int = Query(1, ge=1, le=2),
) -> ForecastResponse:
    """Return per-device and REC-level energy forecasts.

    ``days`` controls how many days of forecast to return (1 = today only,
    2 = today + tomorrow).  The window always starts at today 05:00 UTC.
    """

    participant = await dt.participants.profile(user.sub)
    community_id = participant.membership.community.key

    # Resolve device_id
    device_id: str | None = None
    try:
        assets = await dt.participants.assets(user.sub)
        if assets and assets.items:
            for asset in assets.items:
                if asset.sensor_id:
                    device_id = asset.sensor_id
                    break
    except Exception as exc:
        logger.warning("Failed to fetch assets for %s: %s", user.sub, exc)

    # Time window: today 05:00 → (today + days) 00:00
    tz = timezone.utc
    today_05 = datetime.now(tz).replace(hour=5, minute=0, second=0, microsecond=0)
    tomorrow_midnight = (today_05 + timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)

    async def fetch_meter_forecast():
        try:
            return await dt.participants.fetch_values(
                participant_id=user.sub,
                fetcher_id="total_meters_forecast",
                payload={
                    "start": today_05.isoformat(),
                    "end": tomorrow_midnight.isoformat(),
                },
            )
        except Exception as exc:
            logger.warning("total_meters_forecast fetch failed: %s", exc)
            return None

    async def fetch_user_consumption():
        """Individual meter consumption — shown as 'Your consumption' tab."""
        if not device_id:
            return None
        try:
            return await dt.participants.fetch_values(
                participant_id=user.sub,
                fetcher_id="meter_forecast",
                payload={
                    "device_id": device_id,
                    "start": today_05.isoformat(),
                    "end": tomorrow_midnight.isoformat(),
                },
            )
        except Exception as exc:
            logger.warning("meter_forecast (individual consumption) fetch failed: %s", exc)
            return None

    meter_res, consumption_res = await asyncio.gather(
        fetch_meter_forecast(), fetch_user_consumption()
    )

    # user_forecast = community net exchange (positive = solar surplus available)
    user_forecast: list[ForecastHourItem] = []
    if meter_res and meter_res.count > 0:
        for item in meter_res.items:
            r = item.to_dict()
            ts = r.get("timestamp") or r.get("datetime") or ""
            user_forecast.append(
                ForecastHourItem(
                    ts=_str(ts),
                    value=_float(r.get("net_exchange_kwh")),
                    lower=None,
                    upper=None,
                    period=_str(r.get("period")) or "forecast",
                )
            )

    # rec_forecast = individual meter consumption (repurposed field, same schema)
    rec_forecast: list[ForecastHourItem] = []
    if consumption_res and consumption_res.count > 0:
        for item in consumption_res.items:
            r = item.to_dict()
            ts = r.get("timestamp") or r.get("datetime") or ""
            rec_forecast.append(
                ForecastHourItem(
                    ts=_str(ts),
                    value=_first_value(r, "total_consumption_kwh", "grid_import_kwh") or 0.0,
                    lower=_first_value(r, "total_consumption_lower", "grid_import_lower"),
                    upper=_first_value(r, "total_consumption_upper", "grid_import_upper"),
                    period=_str(r.get("period")) or "forecast",
                )
            )

    return ForecastResponse(
        user_forecast=_sort_dedup(user_forecast),
        rec_forecast=_sort_dedup(rec_forecast),
    )
