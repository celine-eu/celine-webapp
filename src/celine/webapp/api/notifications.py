"""Notification-related API routes."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy import select, desc, delete

from celine.webapp.api.deps import UserDep, DbDep
from celine.webapp.api.schemas import (
    NotificationItem,
    VapidKeyResponse,
    WebPushUnsubscribeRequest,
    SuccessResponse,
)
from celine.webapp.db import WebPushSubscription
from celine.webapp.settings import settings as app_settings


router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationItem])
async def list_notifications(
    user: UserDep,
    db: DbDep,
) -> list[NotificationItem]:
    """List user notifications."""

    # TODO
    @dataclass(frozen=True)
    class TestNotification:
        id: str
        title: str
        body: str
        severity: str
        created_at: datetime
        read_at: datetime | None

    notifications: list[TestNotification] = [
        TestNotification(
            id="0000001",
            created_at=datetime.now(),
            title="Welcome to the REC Webapp (example)",
            body="Learn more about the app from your energy community manager",
            severity="info",
            read_at=None,
        )
    ]

    return [
        NotificationItem(
            id=n.id,
            created_at=n.created_at.isoformat(),
            title=n.title,
            body=n.body,
            severity=(
                "critical"
                if n.severity == "critical"
                else "warning" if n.severity == "warning" else "info"
            ),
            read_at=n.read_at.isoformat() if n.read_at else None,
        )
        for n in notifications
    ]


@router.post("/enable", response_model=SuccessResponse)
async def enable_notifications(
    user: UserDep,
    db: DbDep,
) -> SuccessResponse:
    """Enable notifications for user."""

    # Idempotent placeholder: in a real implementation this might
    # register the user in the nudging tool
    return SuccessResponse()


@router.get("/webpush/vapid-public-key", response_model=VapidKeyResponse)
async def vapid_public_key(
    user: UserDep,
    db: DbDep,
) -> VapidKeyResponse:
    """Get VAPID public key for web push."""
    return VapidKeyResponse(public_key=app_settings.vapid_public_key)


@router.post("/webpush/subscribe", response_model=SuccessResponse)
async def webpush_subscribe(
    request: Request,
    user: UserDep,
    db: DbDep,
) -> SuccessResponse:
    """Subscribe to web push notifications."""

    data = await request.json()
    endpoint = data.get("endpoint")

    if not endpoint:
        raise HTTPException(status_code=400, detail="subscription endpoint missing")

    # Check if subscription already exists
    result = await db.execute(
        select(WebPushSubscription).filter(
            WebPushSubscription.user_id == user.sub,
            WebPushSubscription.endpoint == endpoint,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Update existing subscription
        existing.subscription_json = data
        await db.commit()
    else:
        # Create new subscription
        subscription = WebPushSubscription(
            user_id=user.sub,
            endpoint=endpoint,
            subscription_json=data,
        )
        db.add(subscription)
        await db.commit()

    return SuccessResponse()


@router.post("/webpush/unsubscribe", response_model=SuccessResponse)
async def webpush_unsubscribe(
    body: WebPushUnsubscribeRequest,
    user: UserDep,
    db: DbDep,
) -> SuccessResponse:
    """Unsubscribe from web push notifications."""

    await db.execute(
        delete(WebPushSubscription).filter(
            WebPushSubscription.user_id == user.sub,
            WebPushSubscription.endpoint == body.endpoint,
        )
    )
    await db.commit()

    return SuccessResponse()
