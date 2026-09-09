"""Notification-related API routes."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from celine.sdk.openapi.nudging.errors import UnexpectedStatus

from celine.webapp.api.deps import NudgingDep, UserDep, DbDep
from celine.webapp.api.schemas import (
    NotificationClickTrackPayload,
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

logger = logging.getLogger(__name__)


@router.get("", response_model=list[NotificationItem])
async def list_notifications(
    user: UserDep, db: DbDep, nudging_client: NudgingDep
) -> list[NotificationItem]:
    """List user notifications.

    A token the nudging tool will not accept (401/403) yields an empty list, not a 500:
    the member is authenticated here, and the mismatch is between two services' audience
    configuration — it is logged so it can be chased, and the page still renders. Any
    other unexpected upstream status is the nudging tool's failure, reported as 502.
    """

    try:
        res = await nudging_client.list_notifications()
    except UnexpectedStatus as exc:
        if exc.status_code in (401, 403):
            logger.warning(
                "Nudging rejected the forwarded token for %s with %s; returning no notifications",
                user.sub,
                exc.status_code,
            )
            return []
        logger.error(
            "Nudging list_notifications failed for %s with %s", user.sub, exc.status_code
        )
        raise HTTPException(status_code=502, detail="Notifications unavailable") from exc

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
    unread = await nudging_client.list_notifications(unread_only=True)

    if unread:
        await asyncio.gather(
            *[nudging_client.mark_read(n.id) for n in unread]
        )

    return SuccessResponse()


@router.post("/{notification_id}/read", response_model=SuccessResponse)
async def mark_notification_read(
    notification_id: str,
    user: UserDep,
    nudging_client: NudgingDep,
) -> SuccessResponse:
    """Mark a single notification as read. Idempotent."""
    result = await nudging_client.mark_read(notification_id)
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
    )

    await update_user_settings(
        user_id=user.sub,
        db=db,
        webpush_enabled=False,
    )

    return SuccessResponse()


@router.post("/track-click", response_model=SuccessResponse)
async def track_notification_click(
    user: UserDep,
    nudging_client: NudgingDep,
    payload: NotificationClickTrackPayload,
) -> SuccessResponse:
    client = nudging_client._get_client(None).get_async_httpx_client()
    res = await client.post(
        "/notifications/track-click",
        json={
            "token": payload.token,
            "action": payload.action,
        },
    )
    res.raise_for_status()
    return SuccessResponse()
