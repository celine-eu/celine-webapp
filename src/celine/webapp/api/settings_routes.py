"""User settings API routes."""

from fastapi import APIRouter, Request
from sqlalchemy import select

from celine.webapp.api.deps import UserDep, DbDep
from celine.webapp.api.schemas import SettingsModel
from celine.webapp.db import Settings
from celine.webapp.db.user_settings import load_user_settings, update_user_settings

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings", response_model=SettingsModel)
async def get_settings(
    user: UserDep,
    db: DbDep,
) -> SettingsModel:
    """Get user settings."""
    settings = await load_user_settings(user.sub, db)
    return SettingsModel(
        simple_mode=settings.simple_mode,
        font_scale=settings.font_scale,
        notifications={"email_enabled": settings.email_notifications},
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

    await update_user_settings(
        user_id=user.sub,
        db=db,
        simple_mode=model.simple_mode,
        font_scale=model.font_scale,
        email_notifications=bool(model.notifications.get("email_enabled")),
        webpush_enabled=bool(model.notifications.get("webpush_enabled")),
    )

    return model
