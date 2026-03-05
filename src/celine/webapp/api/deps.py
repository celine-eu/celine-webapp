# celine/webapp/api/deps.py
"""Authentication and service dependencies."""

from typing import Annotated
import logging
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
import jwt as pyjwt

from celine.webapp.settings import settings
from celine.webapp.db import get_db
from celine.sdk.auth import JwtUser
from celine.sdk.auth.static import StaticTokenProvider
from celine.sdk.dt import DTClient
from celine.sdk.nudging.client import NudgingClient

logger = logging.getLogger(__name__)


def _extract_token(request: Request) -> str | None:
    """Read the caller JWT from the oauth2-proxy header or Authorization."""
    token = request.headers.get(settings.jwt_header_name)
    if token:
        return token

    authorization = request.headers.get("authorization")
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    logger.warning(
        "Missing auth headers on %s %s; available=%s",
        request.method,
        request.url.path,
        {
            "authorization": bool(request.headers.get("authorization")),
            settings.jwt_header_name: bool(request.headers.get(settings.jwt_header_name)),
            "x-auth-request-user": bool(request.headers.get("x-auth-request-user")),
            "x-auth-request-email": bool(request.headers.get("x-auth-request-email")),
        },
    )

    return None


def get_user_from_request(request: Request) -> JwtUser:
    """
    Extract and validate user from JWT in request header using celine-sdk.

    The SDK handles JWT parsing, signature verification, and expiry checks.
    """
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    try:
        user = JwtUser.from_token(token, oidc=settings.oidc)
        return user

    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except pyjwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")


def get_raw_token(request: Request) -> str:
    """Extract the raw JWT string from the request header."""
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")
    return token


def get_dt_client(request: Request) -> DTClient:
    """Create a DTClient that forwards the caller's JWT to the DT API.

    The StaticTokenProvider wraps the user's existing JWT — no refresh,
    no client-credentials. The upstream (oauth2_proxy) already validated it.
    """
    if not settings.digital_twin_api_url:
        raise HTTPException(
            status_code=503,
            detail="Digital Twin API not configured",
        )

    raw_token = get_raw_token(request)
    token_provider = StaticTokenProvider(raw_token)

    return DTClient(
        base_url=settings.digital_twin_api_url,
        token_provider=token_provider,
    )


def get_nudging_client(request: Request) -> NudgingClient:
    if not settings.nudging_api_url:
        raise HTTPException(
            status_code=503,
            detail="Nudging API not configured",
        )

    raw_token = get_raw_token(request)

    return NudgingClient(base_url=settings.nudging_api_url, default_token=raw_token)


def get_client_ip(request: Request) -> str:
    """Extract client IP from request headers."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


# Type aliases for dependency injection
UserDep = Annotated[JwtUser, Depends(get_user_from_request)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
DTDep = Annotated[DTClient, Depends(get_dt_client)]
NudgingDep = Annotated[NudgingClient, Depends(get_nudging_client)]
