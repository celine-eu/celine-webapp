import base64
import json
from dataclasses import dataclass
from typing import Any
from fastapi import Request, HTTPException


@dataclass(frozen=True)
class User:
    sub: str
    email: str | None
    name: str | None
    claims: dict[str, Any]


def _b64url_decode(s: str) -> bytes:
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + padding)


def decode_jwt_no_verify(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("Invalid JWT format")
    payload = json.loads(_b64url_decode(parts[1]).decode("utf-8"))
    return payload


def get_user_from_request(request: Request) -> User:
    token = request.headers.get("authorization")
    if not token:
        raise HTTPException(
            status_code=401, detail="Missing X-Auth-Request-Access-Token"
        )

    if "bearer" in token.lower():
        token = token.split(" ")[1]

    try:
        claims = decode_jwt_no_verify(token)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid JWT: {e}")

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="JWT missing sub")

    email = claims.get("email")
    name = claims.get("name") or claims.get("preferred_username")
    return User(
        sub=str(sub),
        email=str(email) if email else None,
        name=str(name) if name else None,
        claims=claims,
    )
