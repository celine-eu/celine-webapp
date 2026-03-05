"""User settings API routes."""

import logging
import re

import httpx
from fastapi import APIRouter, HTTPException, Request, status

from celine.webapp.api.deps import UserDep, DbDep
from celine.webapp.api.schemas import SettingsModel
from celine.webapp.db.user_settings import load_user_settings, update_user_settings
from celine.webapp.settings import settings as app_settings

router = APIRouter(prefix="/api", tags=["settings"])
logger = logging.getLogger(__name__)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


async def _get_nudging_preferences(token: str | None) -> tuple[int, bool, str]:
    if not token or not app_settings.nudging_api_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Nudging API not configured",
        )

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{app_settings.nudging_api_url}/preferences/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        data = response.json()
        max_per_day = int(data["max_per_day"])
        if max_per_day < 1 or max_per_day > 10:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Invalid notification limit returned by nudging service",
            )
        return (
            max_per_day,
            bool(data.get("channel_email", False)),
            str(data.get("email", "") or ""),
        )


async def _update_nudging_preferences(
    token: str | None,
    max_per_day: int,
    channel_email: bool,
    email: str,
) -> None:
    if not token or not app_settings.nudging_api_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Nudging API not configured",
        )

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.put(
            f"{app_settings.nudging_api_url}/preferences/me",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "max_per_day": max_per_day,
                "channel_email": channel_email,
                "email": email,
            },
        )
        response.raise_for_status()


@router.get("/settings", response_model=SettingsModel)
async def get_settings(
    user: UserDep,
    db: DbDep,
) -> SettingsModel:
    """Get user settings."""
    settings = await load_user_settings(user.sub, db)
    try:
        notification_limit, email_enabled, email = await _get_nudging_preferences(user.token)
    except HTTPException:
        raise
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        logger.error("Could not load nudging preferences for %s: %s", user.sub, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not load notification preferences",
        ) from exc

    return SettingsModel(
        simple_mode=settings.simple_mode,
        font_scale=settings.font_scale,
        notifications={
            "email_enabled": email_enabled,
            "email": email,
            "webpush_enabled": settings.webpush_enabled,
            "limit": notification_limit,
        },
    )


@router.put("/settings", response_model=SettingsModel)
async def update_settings(
    request: Request,
    user: UserDep,
    db: DbDep,
) -> SettingsModel:
    """Update user settings."""

    data = await request.json()
    model = SettingsModel.model_validate(data)
    if model.notifications.email_enabled and not EMAIL_RE.match(
        (model.notifications.email or "").strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Email address is required and must be valid",
        )

    await update_user_settings(
        user_id=user.sub,
        db=db,
        simple_mode=model.simple_mode,
        font_scale=model.font_scale,
        email_notifications=model.notifications.email_enabled,
        webpush_enabled=model.notifications.webpush_enabled,
    )

    try:
        await _update_nudging_preferences(
            user.token,
            model.notifications.limit,
            model.notifications.email_enabled,
            model.notifications.email,
        )
    except httpx.HTTPError as exc:
        logger.error("Could not update nudging preferences for %s: %s", user.sub, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not update notification preferences",
        ) from exc

    return model
