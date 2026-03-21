# celine/webapp/api/community.py
"""Community metadata route — GET /api/community."""
import logging

from fastapi import APIRouter, Request

from celine.webapp.api.deps import UserDep, _extract_token
from celine.webapp.api.schemas import CommunityMetaResponse
from celine.webapp.settings import settings
from celine.sdk.rec_registry import RecRegistryUserClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["community"])


def _str(val) -> str | None:
    return str(val) if val is not None else None


@router.get("/community", response_model=CommunityMetaResponse)
async def community_meta(user: UserDep, request: Request) -> CommunityMetaResponse:
    """Return community metadata: name, legal info, contact details, links."""

    detail = None
    try:
        raw_token = _extract_token(request)
        if raw_token and settings.rec_registry_url:
            registry = RecRegistryUserClient(
                base_url=settings.rec_registry_url,
                default_token=raw_token,
            )
            detail = await registry.get_my_community()
    except Exception as exc:
        logger.warning("Failed to fetch community from registry: %s", exc)

    if detail is None:
        return CommunityMetaResponse(key="unknown", name="REC")

    legal = detail.legal or {}
    contact = detail.contact or {}
    links = detail.links or {}

    def _g(d, *keys):
        """Get from a dict or Pydantic model by attribute/key."""
        obj = d
        for k in keys:
            if obj is None:
                return None
            obj = (
                getattr(obj, k, None)
                if hasattr(obj, k)
                else (obj.get(k) if isinstance(obj, dict) else None)
            )
        return obj

    return CommunityMetaResponse(
        key=_str(detail.key) or "unknown",
        name=_str(detail.name) or "REC",
        description=_str(detail.description),
        legal_name=_str(_g(legal, "name")),
        legal_form=_str(_g(legal, "legal_form")),
        vat=_str(_g(legal, "vat")),
        email=_str(_g(contact, "email")),
        pec=_str(_g(contact, "pec")),
        phone=_str(_g(contact, "phone")),
        website=_str(_g(links, "website")),
        terms_url=_str(_g(links, "terms")),
        privacy_url=_str(_g(links, "privacy_policy")),
    )
