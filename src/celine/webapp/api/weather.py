# celine/webapp/api/weather.py
"""Weather route — GET /api/weather."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter

from celine.webapp.api.deps import DTDep, UserDep
from celine.webapp.api.schemas import (
    WeatherAlertItem,
    WeatherCurrent,
    WeatherDayItem,
    WeatherIrradianceItem,
    WeatherResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["weather"])

LOCATION_ID = "it_folgaria"


def _str(val: Any) -> str:
    return str(val) if val is not None else ""


def _float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _int(val: Any, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _normalize_temp(val: Any) -> float:
    t = _float(val)
    if t > 100:  # likely stored as Kelvin
        return round(t - 273.15, 1)
    return t


@router.get("/weather", response_model=WeatherResponse)
async def weather(user: UserDep, dt: DTDep) -> WeatherResponse:
    """Return current conditions, 7-day daily forecast, 24h irradiance, and active alerts."""

    participant = await dt.participants.profile(user.sub)
    community_id = participant.membership.community.key

    now = datetime.now(timezone.utc)
    # Anchor to today midnight UTC so the daily query always includes today's record
    # regardless of what time of day it is.
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = today_midnight + timedelta(days=8)  # inclusive 7-day window
    today_05 = now.replace(hour=5, minute=0, second=0, microsecond=0)
    tomorrow_midnight = (today_05 + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    async def fetch_current():
        try:
            return await dt.communities.fetch_values(
                community_id=community_id,
                fetcher_id="weather_current",
                payload={"location_id": LOCATION_ID},
            )
        except Exception as exc:
            logger.warning("weather_current fetch failed: %s", exc)
            return None

    async def fetch_daily():
        try:
            return await dt.communities.fetch_values(
                community_id=community_id,
                fetcher_id="weather_daily",
                payload={
                    "location_id": LOCATION_ID,
                    "start": today_midnight.isoformat(),
                    "end": week_end.isoformat(),
                },
            )
        except Exception as exc:
            logger.warning("weather_daily fetch failed: %s", exc)
            return None

    async def fetch_alerts():
        try:
            return await dt.communities.fetch_values(
                community_id=community_id,
                fetcher_id="weather_alerts",
                payload={"location_id": LOCATION_ID},
            )
        except Exception as exc:
            logger.warning("weather_alerts fetch failed: %s", exc)
            return None

    async def fetch_irradiance():
        try:
            return await dt.communities.fetch_values(
                community_id=community_id,
                fetcher_id="weather_irradiance_hourly",
                payload={
                    "start": today_05.isoformat(),
                    "end": tomorrow_midnight.isoformat(),
                },
            )
        except Exception as exc:
            logger.warning("weather_irradiance_hourly fetch failed: %s", exc)
            return None

    current_res, daily_res, alerts_res, irradiance_res = await asyncio.gather(
        fetch_current(),
        fetch_daily(),
        fetch_alerts(),
        fetch_irradiance(),
    )

    # Parse current
    current: WeatherCurrent | None = None
    if current_res and current_res.count > 0:
        r = current_res.items[0].to_dict()
        current = WeatherCurrent(
            temp=_normalize_temp(r.get("temp")),
            humidity=_int(r.get("humidity")),
            uvi=_float(r.get("uvi")),
            clouds=_int(r.get("clouds")),
            wind_deg=_int(r.get("wind_deg")),
            weather_main=_str(r.get("weather_main")),
            weather_description=_str(r.get("weather_description")),
            sunrise=_str(r.get("sunrise")),
            sunset=_str(r.get("sunset")),
        )

    # Parse daily
    daily: list[WeatherDayItem] = []
    if daily_res and daily_res.count > 0:
        for item in daily_res.items:
            r = item.to_dict()
            ts = r.get("ts") or r.get("datetime") or ""
            if isinstance(ts, datetime):
                date_str = ts.date().isoformat()
            else:
                date_str = _str(ts)[:10]
            daily.append(
                WeatherDayItem(
                    date=date_str,
                    temp_min=_normalize_temp(r.get("temp_min")),
                    temp_max=_normalize_temp(r.get("temp_max")),
                    temp_day=_normalize_temp(r.get("temp_day")),
                    pop=_float(r.get("pop")),
                    rain=float(r["rain"]) if r.get("rain") is not None else None,
                    clouds=_int(r.get("clouds")),
                    uvi=_float(r.get("uvi")),
                    weather_main=_str(r.get("weather_main")),
                    weather_description=_str(r.get("weather_description")),
                    summary=_str(r.get("summary")) or None,
                )
            )

    # Parse alerts
    alerts: list[WeatherAlertItem] = []
    if alerts_res and alerts_res.count > 0:
        for item in alerts_res.items:
            r = item.to_dict()
            alerts.append(
                WeatherAlertItem(
                    event=_str(r.get("event")),
                    sender_name=_str(r.get("sender_name")),
                    start_ts=_str(r.get("start_ts")),
                    end_ts=_str(r.get("end_ts")),
                    description=_str(r.get("description")),
                )
            )

    # Parse irradiance
    hourly_irradiance: list[WeatherIrradianceItem] = []
    irradiance_date: str | None = None
    if irradiance_res and irradiance_res.count > 0:
        for item in irradiance_res.items:
            r = item.to_dict()
            ts = r.get("datetime") or r.get("ts") or ""
            if irradiance_date is None:
                ts_str = _str(ts)
                irradiance_date = ts_str[:10] if len(ts_str) >= 10 else today.date().isoformat()
            hourly_irradiance.append(
                WeatherIrradianceItem(
                    ts=_str(ts),
                    shortwave_radiation=_float(r.get("shortwave_radiation")),
                    diffuse_radiation=_float(r.get("diffuse_radiation")),
                    global_tilted_irradiance=_float(r.get("global_tilted_irradiance")),
                    cloud_cover=_float(r.get("cloud_cover")),
                )
            )

    if irradiance_date is None and hourly_irradiance:
        irradiance_date = today.date().isoformat()

    return WeatherResponse(
        current=current,
        daily=daily,
        hourly_irradiance=hourly_irradiance,
        alerts=alerts,
        irradiance_date=irradiance_date,
    )
