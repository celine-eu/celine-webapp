"""Feedback API routes."""

import base64
import binascii
from datetime import UTC, datetime
from uuid import UUID

from celine.sdk.auth.jwt import organization_groups, realm_groups
from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import func, select

from celine.webapp.api.deps import DbDep, RegistryDep, UserDep, get_client_ip
from celine.webapp.api.schemas import (
    FeedbackCreateRequest,
    FeedbackCreateResponse,
    FeedbackItemResponse,
    FeedbackListResponse,
    FeedbackState,
    FeedbackStatusCounts,
    FeedbackStatusUpdate,
)
from celine.webapp.db import FeedbackEntry

router = APIRouter(prefix="/api/feedback", tags=["feedback"])
_STATUS_ORDER = {"new": 0, "seen": 1, "resolved": 2}
_SAFE_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _names(groups: list[str]) -> set[str]:
    return {group.strip("/").lower() for group in groups}


def _require_manager(user, community_key: str) -> None:
    """Enforce the same realm/REC boundary used by the manager dashboard."""
    claims = user.claims or {}
    raw_scope = claims.get("scope") or ""
    scopes = set(raw_scope.split() if isinstance(raw_scope, str) else raw_scope)
    if "community.read" not in scopes:
        raise HTTPException(status_code=403, detail="Missing community.read scope")

    if "admins" in _names(realm_groups(claims)):
        return

    organization = user.get_organization(community_key)
    org_type = (organization.type or "").lower() if organization else ""
    groups = _names(organization_groups(claims, community_key))
    if organization and org_type == "rec" and groups.intersection({"admins", "managers"}):
        return
    raise HTTPException(status_code=403, detail="Manager access denied for this REC")


def _response(entry: FeedbackEntry) -> FeedbackItemResponse:
    return FeedbackItemResponse(
        id=str(entry.id),
        rating=entry.rating,
        comment=entry.comment,
        page_url=entry.page_url,
        page_title=entry.page_title,
        page_path=entry.page_path,
        locale=entry.locale,
        timezone=entry.timezone,
        viewport_width=entry.viewport_width,
        viewport_height=entry.viewport_height,
        screen_width=entry.screen_width,
        screen_height=entry.screen_height,
        color_scheme=entry.color_scheme,
        client_timestamp=entry.client_timestamp,
        extra=entry.extra_context or {},
        has_screenshot=entry.screenshot_bytes is not None,
        status=entry.status,
        seen_at=entry.seen_at,
        resolved_at=entry.resolved_at,
        created_at=entry.created_at,
    )


async def _entry(community_key: str, feedback_id: UUID, db: DbDep) -> FeedbackEntry:
    entry = await db.scalar(
        select(FeedbackEntry)
        .where(FeedbackEntry.id == feedback_id)
        .where(FeedbackEntry.community_key == community_key)
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Feedback not found in this REC")
    return entry


@router.post("", response_model=FeedbackCreateResponse, status_code=201)
async def create_feedback(
    request: Request,
    body: FeedbackCreateRequest,
    user: UserDep,
    db: DbDep,
    registry: RegistryDep,
) -> FeedbackCreateResponse:
    """Persist end-user feedback with page diagnostics."""

    try:
        community = await registry.get_my_community()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Unable to resolve user community") from exc
    community_key = str(community.key) if community and community.key else None
    if not community_key:
        raise HTTPException(status_code=409, detail="User has no REC membership")

    screenshot_bytes: bytes | None = None
    screenshot_mime_type: str | None = None

    if body.screenshot:
        try:
            screenshot_bytes = base64.b64decode(body.screenshot.data_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Invalid screenshot payload") from exc

        screenshot_mime_type = body.screenshot.mime_type

    extra_context = dict(body.context.extra)
    extra_context["community_key"] = community_key
    entry = FeedbackEntry(
        community_key=community_key,
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
        extra_context=extra_context,
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


@router.get("/manager/{community_key}", response_model=FeedbackListResponse)
async def list_manager_feedback(
    community_key: str,
    user: UserDep,
    db: DbDep,
    status: FeedbackState | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, alias="pageSize", ge=1, le=100),
) -> FeedbackListResponse:
    """List participant-dashboard feedback for a manager of the requested REC."""
    _require_manager(user, community_key)
    base = FeedbackEntry.community_key == community_key
    counts_result = await db.execute(
        select(FeedbackEntry.status, func.count(FeedbackEntry.id))
        .where(base)
        .group_by(FeedbackEntry.status)
    )
    counts = {name: count for name, count in counts_result.all()}
    filtered = select(FeedbackEntry).where(base)
    total_query = select(func.count(FeedbackEntry.id)).where(base)
    if status:
        filtered = filtered.where(FeedbackEntry.status == status)
        total_query = total_query.where(FeedbackEntry.status == status)
    total = int(await db.scalar(total_query) or 0)
    result = await db.execute(
        filtered.order_by(FeedbackEntry.created_at.desc(), FeedbackEntry.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return FeedbackListResponse(
        community_key=community_key,
        page=page,
        page_size=page_size,
        total=total,
        counts=FeedbackStatusCounts(
            new=int(counts.get("new", 0)),
            seen=int(counts.get("seen", 0)),
            resolved=int(counts.get("resolved", 0)),
        ),
        items=[_response(entry) for entry in result.scalars().all()],
    )


@router.get("/manager/{community_key}/{feedback_id}/screenshot")
async def manager_feedback_screenshot(
    community_key: str,
    feedback_id: UUID,
    user: UserDep,
    db: DbDep,
) -> Response:
    _require_manager(user, community_key)
    entry = await _entry(community_key, feedback_id, db)
    if entry.screenshot_bytes is None:
        raise HTTPException(status_code=404, detail="Feedback screenshot not found")
    media_type = (
        entry.screenshot_mime_type
        if entry.screenshot_mime_type in _SAFE_IMAGE_TYPES
        else "application/octet-stream"
    )
    return Response(content=entry.screenshot_bytes, media_type=media_type)


@router.patch("/manager/{community_key}/{feedback_id}", response_model=FeedbackItemResponse)
async def update_manager_feedback_status(
    community_key: str,
    feedback_id: UUID,
    body: FeedbackStatusUpdate,
    user: UserDep,
    db: DbDep,
) -> FeedbackItemResponse:
    _require_manager(user, community_key)
    entry = await _entry(community_key, feedback_id, db)
    if _STATUS_ORDER[body.status] < _STATUS_ORDER[entry.status]:
        raise HTTPException(status_code=409, detail="Feedback status cannot move backward")
    if body.status == entry.status:
        return _response(entry)
    now = datetime.now(UTC)
    if entry.seen_at is None:
        entry.seen_at = now
    if body.status == "resolved":
        entry.resolved_at = now
    entry.status = body.status
    entry.status_updated_by = user.sub
    await db.commit()
    await db.refresh(entry)
    return _response(entry)
