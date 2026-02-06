"""User settings API routes."""
from fastapi import APIRouter, Request
from sqlalchemy import select

from celine.webapp.api.deps import UserDep, DbDep, ensure_user_exists
from celine.webapp.api.schemas import SettingsModel
from celine.webapp.db import Settings


router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings", response_model=SettingsModel)
async def get_settings(
    user: UserDep,
    db: DbDep,
) -> SettingsModel:
    """Get user settings."""
    await ensure_user_exists(user, db)
    
    result = await db.execute(
        select(Settings).filter(Settings.user_id == user.sub)
    )
    settings = result.scalar_one_or_none()
    
    if not settings:
        settings = Settings(
            user_id=user.sub,
            simple_mode=False,
            font_scale=1.0,
            email_notifications=False,
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    
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
    await ensure_user_exists(user, db)
    
    data = await request.json()
    model = SettingsModel.model_validate(data)
    
    result = await db.execute(
        select(Settings).filter(Settings.user_id == user.sub)
    )
    settings = result.scalar_one_or_none()
    
    if not settings:
        settings = Settings(user_id=user.sub)
        db.add(settings)
    
    settings.simple_mode = model.simple_mode
    settings.font_scale = model.font_scale
    settings.email_notifications = bool(model.notifications.get("email_enabled"))
    
    await db.commit()
    await db.refresh(settings)
    
    return model
