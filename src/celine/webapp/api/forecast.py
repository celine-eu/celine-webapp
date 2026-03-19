# celine/webapp/api/forecast.py
"""Forecast route — GET /api/forecast."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter

from celine.webapp.api.deps import DTDep, UserDep
from celine.webapp.api.schemas import ForecastHourItem, ForecastResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["forecast"])


def _float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _str(val: Any) -> str:
    return str(val) if val is not None else ""


@router.get("/forecast", response_model=ForecastResponse)
async def forecast(user: UserDep, dt: DTDep) -> ForecastResponse:
    """Return 48h per-device and REC-level energy forecasts with confidence bands."""

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

    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=48)

    async def fetch_meter_forecast():
        if not device_id:
            return None
        try:
            return await dt.participants.fetch_values(
                participant_id=user.sub,
                fetcher_id="meter_forecast",
                payload={
                    "device_id": device_id,
                    "start": now.isoformat(),
                    "end": end.isoformat(),
                },
            )
        except Exception as exc:
            logger.warning("meter_forecast fetch failed: %s", exc)
            return None

    async def fetch_rec_forecast():
        try:
            return await dt.communities.fetch_values(
                community_id=community_id,
                fetcher_id="rec_forecast",
                payload={
                    "start": now.isoformat(),
                    "end": end.isoformat(),
                },
            )
        except Exception as exc:
            logger.warning("rec_forecast fetch failed: %s", exc)
            return None

    meter_res, rec_res = await asyncio.gather(fetch_meter_forecast(), fetch_rec_forecast())

    user_forecast: list[ForecastHourItem] = []
    if meter_res and meter_res.count > 0:
        for item in meter_res.items:
            r = item.to_dict()
            ts = r.get("timestamp") or r.get("datetime") or ""
            user_forecast.append(
                ForecastHourItem(
                    ts=_str(ts),
                    value=_float(r.get("total_consumption_kwh")),
                    lower=float(r["total_consumption_lower"]) if r.get("total_consumption_lower") is not None else None,
                    upper=float(r["total_consumption_upper"]) if r.get("total_consumption_upper") is not None else None,
                    period=_str(r.get("period")) or "forecast",
                )
            )

    rec_forecast: list[ForecastHourItem] = []
    if rec_res and rec_res.count > 0:
        for item in rec_res.items:
            r = item.to_dict()
            ts = r.get("datetime") or r.get("ts") or ""
            rec_forecast.append(
                ForecastHourItem(
                    ts=_str(ts),
                    value=_float(r.get("prediction")),
                    lower=float(r["lower"]) if r.get("lower") is not None else None,
                    upper=float(r["upper"]) if r.get("upper") is not None else None,
                    period=_str(r.get("period")) or "forecast",
                )
            )

    return ForecastResponse(user_forecast=user_forecast, rec_forecast=rec_forecast)
