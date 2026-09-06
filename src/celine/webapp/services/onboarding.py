"""Onboarding's member-facing surface, reached as the member.

Onboarding owns everything to do with a member's dataspace identity: it
resolves their credential, it speaks to the connector, and it holds the grants
that let it. This service does not, and must not — a backend-for-frontend that
holds a credential it has no use for is a credential in one more place.

So the only thing this client carries is **the caller's own JWT**, forwarded
unchanged, exactly as `get_dt_client` and `get_nudging_client` do. There is no
service account here and adding one would defeat the point: a route that an
operator's token could reach is a route that can act on somebody else's consent.

The frontend never talks to onboarding directly. It is not same-origin, and
keeping the browser on one origin is the reason this repository exists.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class OnboardingUnavailable(RuntimeError):
    """Onboarding could not be reached.

    Transport only. A response this service dislikes is the caller's to read:
    the status onboarding answers with is part of what gets proxied, and
    flattening 409 into "unavailable" would lose the distinction between "this
    offer cannot be toggled" and "the service is down".
    """


class OnboardingClient:
    """Thin HTTP client for onboarding, authenticated as the caller.

    Deliberately not a method per endpoint. The routes it serves are proxies,
    and a wrapper that re-declares onboarding's response shapes here would be a
    second copy of a contract this service does not own.
    """

    def __init__(self, base_url: str, token: str, *, timeout: float = 15.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        return self._base_url

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Call onboarding as the member, and hand back what it answered."""
        headers = {
            "Authorization": f"Bearer {self._token}",
            **(kwargs.pop("headers", None) or {}),
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                return await client.request(
                    method, self._url(path), headers=headers, **kwargs
                )
        except httpx.HTTPError as exc:
            raise OnboardingUnavailable(f"Onboarding unreachable: {exc}") from exc

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", path, **kwargs)
