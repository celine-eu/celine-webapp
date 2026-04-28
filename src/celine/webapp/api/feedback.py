"""Feedback API routes."""

import base64
import binascii
from fastapi import APIRouter, HTTPException, Request

from celine.webapp.api.deps import DbDep, UserDep, get_client_ip
from celine.webapp.api.schemas import FeedbackCreateRequest, FeedbackCreateResponse
from celine.webapp.db import FeedbackEntry


router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackCreateResponse, status_code=201)
async def create_feedback(
    request: Request,
    body: FeedbackCreateRequest,
    user: UserDep,
    db: DbDep,
) -> FeedbackCreateResponse:
    """Persist end-user feedback with page diagnostics."""

    screenshot_bytes: bytes | None = None
    screenshot_mime_type: str | None = None

    if body.screenshot:
        try:
            screenshot_bytes = base64.b64decode(body.screenshot.data_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Invalid screenshot payload") from exc

        screenshot_mime_type = body.screenshot.mime_type

    entry = FeedbackEntry(
        user_id=user.sub,
        rating=body.rating,
        comment=body.comment.strip() or None,
        page_url=body.context.page_url,
        page_title=body.context.page_title,
        page_path=body.context.page_path,
        locale=body.context.locale,
        timezone=body.context.timezone,
        user_agent=body.context.user_agent,
        viewport_width=body.context.viewport_width,
        viewport_height=body.context.viewport_height,
        screen_width=body.context.screen_width,
        screen_height=body.context.screen_height,
        color_scheme=body.context.color_scheme,
        client_timestamp=body.context.client_timestamp,
        client_ip=get_client_ip(request),
        extra_context=body.context.extra or None,
        screenshot_mime_type=screenshot_mime_type,
        screenshot_bytes=screenshot_bytes,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    return FeedbackCreateResponse(
        id=str(entry.id),
        created_at=entry.created_at,
    )
