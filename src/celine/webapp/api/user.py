"""User-related API routes."""

from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from celine.webapp import legal
from celine.webapp.api.deps import UserDep, DbDep, _extract_token, get_client_ip
from celine.webapp.api.schemas import (
    LegalDocumentOut,
    MeResponse,
    AcceptTermsRequest,
    OnboardingSeenRequest,
    SuccessResponse,
)
from celine.webapp.db import (
    PolicyAcceptance,
    Settings,
)
from celine.webapp.db.user_settings import (
    list_onboarding_seen_pages,
    mark_onboarding_page_seen,
)
from celine.webapp.settings import settings as app_settings


router = APIRouter(prefix="/api", tags=["user"])


@router.get("/ping", include_in_schema=False)
async def ping(user: UserDep) -> dict:
    return {"ok": True}


async def get_accepted_policy_version(user_id: str, db: AsyncSession) -> str | None:
    """The policy version the user accepted most recently, if any.

    Every version accepted is a row of its own, so a user who accepted again after a
    version change has several: read the newest, never expect exactly one.
    """
    result = await db.execute(
        select(PolicyAcceptance)
        .filter(PolicyAcceptance.user_id == user_id, PolicyAcceptance.document.is_(None))
        .order_by(PolicyAcceptance.accepted_at.desc())
        .limit(1)
    )
    acceptance = result.scalars().first()
    return acceptance.policy_version if acceptance else None


async def _latest_acceptance(
    user_id: str, community_key: str, document: str, db: AsyncSession
) -> PolicyAcceptance | None:
    result = await db.execute(
        select(PolicyAcceptance)
        .filter(
            PolicyAcceptance.user_id == user_id,
            PolicyAcceptance.community_key == community_key,
            PolicyAcceptance.document == document,
        )
        .order_by(PolicyAcceptance.accepted_at.desc())
        .limit(1)
    )
    return result.scalars().first()


async def community_documents(
    request: Request, user_sub: str, db: AsyncSession
) -> tuple[str, list[tuple[legal.LegalDocument, bool]]] | None:
    """With a legal host and a known community: each gate document and whether it must be
    accepted (`celine.webapp.legal`). None: the deployment-wide `POLICY_VERSION` applies."""
    base = app_settings.legal_base_url
    if not base:
        return None
    key = await legal.community_key_of(user_sub, _extract_token(request), app_settings.rec_registry_url)
    if not key:
        return None
    known = await legal.current(base, key)
    documents = legal.gate_documents(base, key, known, legal.locales_from(request.headers.get("accept-language")))
    out = []
    for document in documents:
        row = await _latest_acceptance(user_sub, key, document.document, db)
        out.append((document, legal.needs_acceptance(
            document,
            row.policy_version if row else None,
            row.accepted_at if row else None,
            row is not None,
        )))
    return key, out


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
    legal_documents = None
    per_document = await community_documents(request, user.sub, db)
    if per_document is not None:
        _, documents = per_document
        legal_documents = [
            LegalDocumentOut(document=d.document, url=d.url, version=d.version, title=d.title, required=needed)
            for d, needed in documents
        ]
        required = any(needed for _, needed in documents)
    settings = await get_user_settings(user.sub, db)
    onboarding_seen_pages = await list_onboarding_seen_pages(user.sub, db)

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
        legal_documents=legal_documents,
        simple_mode=settings.simple_mode,
        font_scale=settings.font_scale,
        notification_permission=notification_permission,
        webpush_configured=settings.webpush_enabled,
        onboarding_seen=settings.onboarding_seen_at is not None,
        onboarding_seen_pages=onboarding_seen_pages,
        data_sharing_enabled=app_settings.data_sharing_ready,
    )


@router.post("/onboarding/seen", response_model=SuccessResponse)
async def onboarding_seen(
    body: OnboardingSeenRequest,
    user: UserDep,
    db: DbDep,
) -> SuccessResponse:
    """Mark one in-app onboarding page as seen for the current user."""
    await mark_onboarding_page_seen(user.sub, body.page_key, db)
    return SuccessResponse()


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

    per_document = await community_documents(request, user.sub, db)
    if per_document is not None:
        key, documents = per_document
        shown = {d.document: d.version for d in body.documents or []}
        now = datetime.now(timezone.utc)
        for document, needed in documents:
            if not needed:
                continue
            # The version recorded is the one this service shows, never the client's;
            # a client naming another one saw an older page.
            sent = shown.get(document.document)
            if document.version is not None and sent is not None and sent != document.version:
                raise HTTPException(
                    status_code=409,
                    detail=f"{document.document}: version {sent} was shown, the current one is "
                    f"{document.version}; reload the page",
                )
            db.add(PolicyAcceptance(
                user_id=user.sub,
                policy_version=document.version,
                accepted_at=now,
                accepted_from_ip=get_client_ip(request),
                community_key=key,
                document=document.document,
                locale=document.locale,
                document_url=document.url,
                document_sha256=document.sha256,
            ))
        await db.commit()
        return SuccessResponse()

    # Already accepted this version? (`first`, not `one`: nothing makes the pair unique.)
    result = await db.execute(
        select(PolicyAcceptance)
        .filter(
            PolicyAcceptance.user_id == user.sub,
            PolicyAcceptance.policy_version == app_settings.policy_version,
        )
        .limit(1)
    )
    existing = result.scalars().first()

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
