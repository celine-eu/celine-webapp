"""Notification-related API routes."""

import asyncio
from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from celine.webapp.api.deps import NudgingDep, UserDep, DbDep
from celine.webapp.api.schemas import (
    NotificationItem,
    PushSubscriptionPayload,
    PushSubscriptionUnsubscribePayload,
    VapidKeyResponse,
    SuccessResponse,
)
from celine.webapp.db.user_settings import update_user_settings

from celine.sdk.openapi.nudging.models import (
    SubscribeRequest,
    WebPushSubscriptionIn,
    WebPushKeysIn,
    UnsubscribeRequest,
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationItem])
async def list_notifications(
    user: UserDep, db: DbDep, nudging_client: NudgingDep
) -> list[NotificationItem]:
    """List user notifications."""

    res = await nudging_client.list_notifications(token=user.token)

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
            deleted_at=n.deleted_at.isoformat() if n.deleted_at else None,
        )
        for n in res
    ]


@router.post("/enable", response_model=SuccessResponse)
async def enable_notifications(
    user: UserDep,
    db: DbDep,
) -> SuccessResponse:
    # TODO
    await update_user_settings(user_id=user.sub, db=db, email_notifications=True)
    return SuccessResponse()


@router.post("/disable", response_model=SuccessResponse)
async def disable_notifications(
    user: UserDep,
    db: DbDep,
) -> SuccessResponse:
    # TODO
    await update_user_settings(user_id=user.sub, db=db, email_notifications=False)
    return SuccessResponse()


# NOTE: /read-all must be registered before /{id}/read so FastAPI does not
# capture the literal string "read-all" as a notification id.
@router.post("/read-all", response_model=SuccessResponse)
async def mark_all_notifications_read(
    user: UserDep,
    nudging_client: NudgingDep,
) -> SuccessResponse:
    """Mark every unread notification as read for the current user.

    The nudging service has no bulk-mark-read endpoint, so we fetch the
    unread list and fan out individual mark_read calls concurrently.
    """
    unread = await nudging_client.list_notifications(unread_only=True, token=user.token)

    if unread:
        await asyncio.gather(
            *[nudging_client.mark_read(n.id, token=user.token) for n in unread]
        )

    return SuccessResponse()


@router.post("/{notification_id}/read", response_model=SuccessResponse)
async def mark_notification_read(
    notification_id: str,
    user: UserDep,
    nudging_client: NudgingDep,
) -> SuccessResponse:
    """Mark a single notification as read. Idempotent."""
    result = await nudging_client.mark_read(notification_id, token=user.token)
    if result is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return SuccessResponse()


@router.get("/webpush/vapid-public-key", response_model=VapidKeyResponse)
async def vapid_public_key(
    nudging_client: NudgingDep,
) -> VapidKeyResponse:
    """Get VAPID public key for web push."""
    res = await nudging_client.get_vapid_public_key()
    if res is None:
        raise HTTPException(500, "Failed to fetch VAPID public key")
    return VapidKeyResponse(public_key=res.public_key)


@router.post("/webpush/subscribe", response_model=SuccessResponse)
async def webpush_subscribe(
    user: UserDep,
    db: DbDep,
    nudging_client: NudgingDep,
    payload: PushSubscriptionPayload,
) -> SuccessResponse:
    """Enable notifications for user."""
    await nudging_client.subscribe(
        body=SubscribeRequest(
            subscription=WebPushSubscriptionIn(
                endpoint=payload.endpoint,
                keys=WebPushKeysIn(
                    p256dh=payload.p256dh,
                    auth=payload.auth,
                ),
            )
        ),
        token=user.token,
    )

    await update_user_settings(
        user_id=user.sub,
        db=db,
        webpush_enabled=True,
    )

    return SuccessResponse()


@router.post("/webpush/unsubscribe", response_model=SuccessResponse)
async def webpush_unsubscribe(
    user: UserDep,
    db: DbDep,
    nudging_client: NudgingDep,
    payload: PushSubscriptionUnsubscribePayload,
) -> SuccessResponse:
    await nudging_client.unsubscribe(
        body=UnsubscribeRequest(endpoint=payload.endpoint),
        token=user.token,
    )

    await update_user_settings(
        user_id=user.sub,
        db=db,
        webpush_enabled=False,
    )

    return SuccessResponse()
