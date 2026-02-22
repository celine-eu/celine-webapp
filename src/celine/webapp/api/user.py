"""User-related API routes."""

from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from celine.webapp.api.deps import UserDep, DbDep, get_client_ip
from celine.webapp.api.schemas import (
    MeResponse,
    AcceptTermsRequest,
    SuccessResponse,
)
from celine.webapp.db import (
    PolicyAcceptance,
    Settings,
)
from celine.webapp.settings import settings as app_settings


router = APIRouter(prefix="/api", tags=["user"])


async def get_accepted_policy_version(user_id: str, db: AsyncSession) -> str | None:
    """Get the accepted policy version for a user."""
    result = await db.execute(
        select(PolicyAcceptance)
        .filter(PolicyAcceptance.user_id == user_id)
        .order_by(PolicyAcceptance.accepted_at.desc())
    )
    acceptance = result.scalar_one_or_none()
    return acceptance.policy_version if acceptance else None


async def terms_required_for(user_id: str, db: AsyncSession) -> tuple[bool, str | None]:
    """
    Check if terms acceptance is required.
    Returns (required: bool, accepted_version: str | None)
    """
    accepted = await get_accepted_policy_version(user_id, db)
    required = accepted != app_settings.policy_version
    return required, accepted


async def get_user_settings(user_id: str, db: AsyncSession) -> Settings:
    """Get or create user settings."""
    result = await db.execute(select(Settings).filter(Settings.user_id == user_id))
    settings_obj = result.scalar_one_or_none()

    if not settings_obj:
        settings_obj = Settings(
            user_id=user_id,
            simple_mode=False,
            font_scale=1.0,
            email_notifications=False,
        )
        db.add(settings_obj)
        await db.commit()
        await db.refresh(settings_obj)

    return settings_obj


@router.get("/me", response_model=MeResponse)
async def me(
    request: Request,
    user: UserDep,
    db: DbDep,
) -> MeResponse:
    """Get current user information."""

    required, accepted_version = await terms_required_for(user.sub, db)
    settings = await get_user_settings(user.sub, db)

    notification_permission = request.headers.get(
        "X-REC-Notification-Permission", "default"
    )
    if notification_permission != "default":
        notification_permission = (
            "granted" if notification_permission == "granted" else "denied"
        )

    return MeResponse(
        user={"sub": user.sub, "email": user.email, "name": user.name},
        terms_required=required,
        policy_version=app_settings.policy_version,
        accepted_policy_version=accepted_version,
        simple_mode=settings.simple_mode,
        font_scale=settings.font_scale,
        notification_permission=notification_permission,
        webpush_configured=settings.webpush_enabled,
    )


@router.post("/terms/accept", response_model=SuccessResponse)
async def accept_terms(
    request: Request,
    body: AcceptTermsRequest,
    user: UserDep,
    db: DbDep,
) -> SuccessResponse:
    """Accept terms and conditions."""

    if not body.accept:
        raise HTTPException(status_code=400, detail="accept must be true")

    # Check if already accepted
    result = await db.execute(
        select(PolicyAcceptance).filter(
            PolicyAcceptance.user_id == user.sub,
            PolicyAcceptance.policy_version == app_settings.policy_version,
        )
    )
    existing = result.scalar_one_or_none()

    if not existing:
        acceptance = PolicyAcceptance(
            user_id=user.sub,
            policy_version=app_settings.policy_version,
            accepted_at=datetime.now(timezone.utc),
            accepted_from_ip=get_client_ip(request),
        )
        db.add(acceptance)
        await db.commit()

    return SuccessResponse()
