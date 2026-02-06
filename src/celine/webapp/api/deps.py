"""Authentication and user dependencies."""

import json
from typing import Annotated
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from celine.webapp.settings import settings
from celine.webapp.db import get_db, User as DBUser


class User(BaseModel):
    """User from JWT token."""

    sub: str
    email: str
    name: str


def get_user_from_request(request: Request) -> User:
    """
    Extract and validate user from JWT in request header.

    This is a minimal JWT extraction without signature verification,
    assuming oauth2_proxy or similar has already validated the token.
    """
    token = request.headers.get(settings.jwt_header_name)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    if "bearer" in token.lower():
        token = token.split(" ")[1]

    # Split JWT and decode payload (without verification)
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid JWT format")

        # Decode payload (add padding if needed)
        payload_b64 = parts[1]
        padding = 4 - (len(payload_b64) % 4)
        if padding != 4:
            payload_b64 += "=" * padding

        import base64

        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes)

        print()

        # Extract user info
        sub = payload.get("sub")
        email = payload.get("email")
        name = payload.get("name") or email

        if not sub or not email:
            raise ValueError("Missing required claims")

        return User(sub=sub, email=email, name=name)

    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


async def ensure_user_exists(user: User, db: AsyncSession) -> DBUser:
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
UserDep = Annotated[User, Depends(get_user_from_request)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
