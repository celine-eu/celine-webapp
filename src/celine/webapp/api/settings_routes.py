"""User settings API routes."""

import logging
import re

from fastapi import APIRouter, HTTPException, Request, status

from celine.webapp.api.deps import UserDep, DbDep, NudgingDep
from celine.webapp.api.schemas import SettingsModel
from celine.webapp.db.user_settings import load_user_settings, update_user_settings

router = APIRouter(prefix="/api", tags=["settings"])
logger = logging.getLogger(__name__)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _preferred_lang(request: Request) -> str | None:
    header = request.headers.get("accept-language", "")
    for chunk in header.split(","):
        lang = chunk.split(";")[0].strip().lower()
        if not lang:
            continue
        base = lang.split("-")[0]
        if base in {"it", "en", "es"}:
            return base
    return None


@router.get("/settings", response_model=SettingsModel)
async def get_settings(
    request: Request,
    user: UserDep,
    db: DbDep,
    nudging_client: NudgingDep,
    lang: str | None = None,
) -> SettingsModel:
    """Get user settings."""
    user_settings = await load_user_settings(user.sub, db)
    catalog: list[dict] = []
    try:
        prefs = await nudging_client.get_preferences()
        notification_limit = int(prefs.max_per_day)
        if notification_limit < 1 or notification_limit > 10:
            notification_limit = 3
        email_enabled = bool(getattr(prefs, "channel_email", False))
        email = str(getattr(prefs, "email", "") or "")
    except Exception as exc:
        logger.error("Could not load nudging preferences for %s: %s", user.sub, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not load notification preferences",
        ) from exc

    try:
        catalog = await nudging_client.get_preference_catalog(
            lang=lang or _preferred_lang(request)
        )
    except Exception as exc:
        logger.warning(
            "Could not load nudging notification catalog for %s: %s",
            user.sub,
            exc,
        )

    return SettingsModel(
        simple_mode=user_settings.simple_mode,
        font_scale=user_settings.font_scale,
        notifications={
            "email_enabled": email_enabled,
            "email": email,
            "webpush_enabled": user_settings.webpush_enabled,
            "limit": notification_limit,
            "kinds": catalog,
        },
    )


@router.put("/settings", response_model=SettingsModel)
async def update_settings(
    request: Request,
    user: UserDep,
    db: DbDep,
    nudging_client: NudgingDep,
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
        await nudging_client.update_preferences(
            max_per_day=model.notifications.limit,
            channel_email=model.notifications.email_enabled,
            email=model.notifications.email,
            enabled_notification_kinds=[
                item.kind for item in model.notifications.kinds if item.enabled
            ],
        )
    except Exception as exc:
        logger.warning(
            "Could not update nudging notification kinds for %s, retrying without kinds: %s",
            user.sub,
            exc,
        )
        try:
            await nudging_client.update_preferences(
                max_per_day=model.notifications.limit,
                channel_email=model.notifications.email_enabled,
                email=model.notifications.email,
            )
        except Exception as fallback_exc:
            logger.error(
                "Could not update nudging preferences for %s: %s",
                user.sub,
                fallback_exc,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not update notification preferences",
            ) from fallback_exc

    return model
