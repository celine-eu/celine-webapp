"""Authentication and user dependencies."""

import json
from typing import Annotated
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from celine.webapp.settings import settings
from celine.webapp.db import get_db, User as DBUser
from celine.sdk.auth import JwtUser


def get_user_from_request(request: Request) -> JwtUser:
    """
    Extract and validate user from JWT in request header using celine-sdk.

    The SDK handles JWT parsing and claim extraction.
    """
    token = request.headers.get(settings.jwt_header_name)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    try:
        # Use SDK to parse JWT (no verification - oauth2_proxy already verified)
        user = JwtUser.from_token(token, verify=False)
        return user

    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


async def ensure_user_exists(user: JwtUser, db: AsyncSession) -> DBUser:
    """
    Ensure user exists in database, create if not.
    Returns the database user object.
    """
    result = await db.execute(select(DBUser).filter(DBUser.sub == user.sub))
    db_user = result.scalar_one_or_none()

    if not db_user:
        db_user = DBUser(
            sub=user.sub,
            email=user.email,
            name=user.name,
        )
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)

    return db_user


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
