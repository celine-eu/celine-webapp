"""User settings API routes."""

import logging

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError

from celine.webapp.api.deps import UserDep, DbDep, NudgingDep
from celine.webapp.api.schemas import SettingsModel
from celine.webapp.db.user_settings import load_user_settings, update_user_settings

router = APIRouter(prefix="/api", tags=["settings"])
logger = logging.getLogger(__name__)
SUPPORTED_NOTIFICATION_LANGS = {"it", "en", "es"}


def _validation_detail(exc: ValidationError) -> str:
    """The first validation message, as a plain string.

    The 422 for this route carries a string `detail` that the app displays directly, not
    FastAPI's array of error objects — so the message is unwrapped here rather than
    letting the default handler shape it. Pydantic prefixes messages raised from a
    validator with "Value error, "; that prefix is noise to a member reading it.
    """
    errors = exc.errors()
    if not errors:
        return "Settings payload is invalid"
    message = str(errors[0].get("msg", "")).removeprefix("Value error, ").strip()
    return message or "Settings payload is invalid"


def _normalize_lang(lang: str | None) -> str | None:
    if not lang:
        return None
    base = lang.strip().lower().split("-")[0]
    if base in SUPPORTED_NOTIFICATION_LANGS:
        return base
    return None


def _preferred_lang(request: Request) -> str | None:
    header = request.headers.get("accept-language", "")
    for chunk in header.split(","):
        normalized = _normalize_lang(chunk.split(";")[0])
        if normalized:
            return normalized
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
    lang: str | None = None,
) -> SettingsModel:
    """Update user settings."""

    data = await request.json()
    try:
        model = SettingsModel.model_validate(data)
    except ValidationError as exc:
        # The body is read here rather than declared as a parameter, so FastAPI's
        # dependency layer never validates it and never raises the
        # RequestValidationError it knows how to turn into a 422. A raw ValidationError
        # escaping this handler is an unhandled exception, which the caller receives as a
        # 500 — a mistyped email address rendered as an outage.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_validation_detail(exc),
        ) from exc

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
            lang=_normalize_lang(lang) or _preferred_lang(request),
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
                lang=_normalize_lang(lang) or _preferred_lang(request),
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
