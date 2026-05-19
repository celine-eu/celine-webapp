"""User settings helpers.

Single place for all get/update operations on the Settings model.
Always upserts - callers never need to worry about whether the row exists.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from celine.webapp.db.models import Settings, UserOnboardingView


async def load_user_settings(user_id: str, db: AsyncSession) -> Settings:
    """Return the Settings row for user_id, creating it with defaults if absent."""
    result = await db.execute(select(Settings).filter(Settings.user_id == user_id))
    settings = result.scalar_one_or_none()

    if settings is None:
        settings = Settings(
            user_id=user_id,
            simple_mode=False,
            font_scale=1.0,
            email_notifications=False,
            webpush_enabled=False,
            onboarding_seen_at=None,
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)

    return settings


async def set_webpush_enabled(
    user_id: str, enabled: bool, db: AsyncSession
) -> Settings:
    """Flip the webpush_enabled flag, creating the settings row if needed."""
    settings = await load_user_settings(user_id, db)
    settings.webpush_enabled = enabled
    await db.commit()
    await db.refresh(settings)
    return settings


async def mark_onboarding_seen(user_id: str, db: AsyncSession) -> Settings:
    """Mark the in-app onboarding as seen for the user."""
    settings = await load_user_settings(user_id, db)
    if settings.onboarding_seen_at is None:
        settings.onboarding_seen_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(settings)
    return settings


async def list_onboarding_seen_pages(user_id: str, db: AsyncSession) -> list[str]:
    """Return page keys for completed onboarding tours."""
    result = await db.execute(
        select(UserOnboardingView.page_key).filter(
            UserOnboardingView.user_id == user_id
        )
    )
    return list(result.scalars().all())


async def mark_onboarding_page_seen(
    user_id: str, page_key: str, db: AsyncSession
) -> UserOnboardingView:
    """Mark one onboarding page as completed for a user."""
    result = await db.execute(
        select(UserOnboardingView).filter(
            UserOnboardingView.user_id == user_id,
            UserOnboardingView.page_key == page_key,
        )
    )
    view = result.scalar_one_or_none()
    if view is None:
        view = UserOnboardingView(user_id=user_id, page_key=page_key)
        db.add(view)
        await db.commit()
        await db.refresh(view)
    return view


async def update_user_settings(
    user_id: str,
    db: AsyncSession,
    *,
    simple_mode: bool | None = None,
    font_scale: float | None = None,
    email_notifications: bool | None = None,
    webpush_enabled: bool | None = None,
) -> Settings:
    """Partial update of any settings fields, creating the row if needed."""
    settings = await load_user_settings(user_id, db)

    if simple_mode is not None:
        settings.simple_mode = simple_mode
    if font_scale is not None:
        settings.font_scale = font_scale
    if email_notifications is not None:
        settings.email_notifications = email_notifications
    if webpush_enabled is not None:
        settings.webpush_enabled = webpush_enabled

    await db.commit()
    await db.refresh(settings)
    return settings
