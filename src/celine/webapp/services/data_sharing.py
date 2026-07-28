"""A member's data-sharing decisions, read and changed as themselves.

The wizard that onboards a participant records an optional consent to share
their energy data into the dataspace. Nothing let them change it afterwards —
onboarding holds no session once somebody is approved, and no credential. This
module is where withdrawal lives, which GDPR Art. 7(3) requires to be as easy as
giving.

**The member acts as themselves.** The connector authenticates a data subject by
verifiable credential (``X-Subject-Id`` + ``X-User-VC``), not by a service token.
So the only thing done on the member's behalf is *resolving* which credential is
theirs; every decision is then presented with that credential. A service account
that could grant consent for somebody would defeat the point of recording it.

Three things worth knowing before changing this:

* **Select the credential by role.** One person legitimately holds several — the
  registry returns them all, and the singular `role`/`vc_jws` fields are the most
  recent one, which is the wrong one as often as not.
* **Never cache a credential across requests**, and never put one in a response.
  It authenticates as that person.
* **Only consent-based offers get a control.** A contract-based offer is
  disclosed, not toggled: presenting a choice that does not exist is what
  invalidates consent, and the connector answers 409 if you try.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from celine.webapp.settings import settings

logger = logging.getLogger(__name__)

DATA_SUBJECT_ROLE = "DataSubject"

_token_provider: Any | None = None


class DataSharingUnavailable(RuntimeError):
    """The dataspace could not be reached, or is not configured."""


class NoDataspaceIdentity(RuntimeError):
    """This member has no dataspace identity.

    Expected, not exceptional: participants enabled before the integration
    existed have none, and neither does anyone in a community that does not
    take part. The UI shows an explanation rather than an error.
    """


@dataclass(frozen=True)
class SubjectCredential:
    """What a member needs in order to act on their own consent."""

    subject_id: str
    vc_jws: str

    @property
    def headers(self) -> dict[str, str]:
        return {"X-Subject-Id": self.subject_id, "X-User-VC": self.vc_jws}


def _resolve_token_provider():
    """Service account used *only* to look up which credential is the member's."""
    global _token_provider
    if _token_provider is None:
        from celine.sdk.auth import OidcClientCredentialsProvider

        _token_provider = OidcClientCredentialsProvider(
            base_url=settings.oidc.base_url,
            client_id=settings.ds_resolve_client_id,
            client_secret=settings.ds_resolve_client_secret,
        )
    return _token_provider


async def resolve_subject(email: str) -> SubjectCredential:
    """Find the member's dataspace DID and their DataSubject credential.

    Raises :class:`NoDataspaceIdentity` when they have none — which is a normal
    state for a participant enabled before the dataspace existed.
    """
    if not settings.identity_registry_url:
        raise DataSharingUnavailable("Identity registry is not configured")

    base = settings.identity_registry_url.rstrip("/")
    try:
        token = await _resolve_token_provider().get_token()
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{base}/users/resolve",
                params={"email": email},
                headers={"Authorization": f"Bearer {token.access_token}"},
            )
    except httpx.HTTPError as exc:
        raise DataSharingUnavailable(f"Identity registry unreachable: {exc}") from exc

    if resp.status_code == 404:
        raise NoDataspaceIdentity(email)
    if resp.status_code >= 400:
        raise DataSharingUnavailable(
            f"Identity registry answered {resp.status_code}"
        )

    body = resp.json()
    subject_id = body.get("did") or body.get("subject_did")

    # Pick the credential for the role this operation needs. Reading the
    # singular `vc_jws` would take whichever was issued last, which for somebody
    # who also holds a consumer credential is the wrong one.
    vc_jws = None
    for credential in body.get("credentials") or []:
        if credential.get("role") == DATA_SUBJECT_ROLE and credential.get("vc_jws"):
            vc_jws = credential["vc_jws"]
            break
    if vc_jws is None and body.get("role") == DATA_SUBJECT_ROLE:
        vc_jws = body.get("vc_jws")

    if not subject_id or not vc_jws:
        raise NoDataspaceIdentity(email)

    return SubjectCredential(subject_id=subject_id, vc_jws=vc_jws)


async def list_offers() -> list[dict[str, Any]]:
    """The published sharing vocabulary.

    Public, and deliberately so — an onboarding flow has to render offers before
    anyone has an identity. Rendered from here rather than from a local copy:
    two copies of the text a person agrees to is how the thing displayed and the
    thing recorded drift apart, invisibly.
    """
    base = (settings.ds_ns_url or settings.ds_connector_url or "").rstrip("/")
    if not base:
        raise DataSharingUnavailable("No sharing-offers vocabulary is configured")

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{base}/ns/sharing-offers")
            resp.raise_for_status()
            return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise DataSharingUnavailable(
            f"Sharing offers could not be read: {exc}"
        ) from exc


async def list_decisions(credential: SubjectCredential) -> list[dict[str, Any]]:
    """The member's current decisions, with the evidence behind each."""
    base = (settings.ds_connector_url or "").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{base}/consent/my/shares", headers=credential.headers
            )
    except httpx.HTTPError as exc:
        raise DataSharingUnavailable(f"Connector unreachable: {exc}") from exc

    if resp.status_code >= 400:
        raise DataSharingUnavailable(f"Connector answered {resp.status_code}")

    body = resp.json()
    return body if isinstance(body, list) else body.get("items", [])


async def set_decision(
    credential: SubjectCredential, offer_id: str, *, enabled: bool
) -> dict[str, Any]:
    """Grant or withdraw one offer, as the member.

    No evidence record is sent. The connector derives it from the resolved offer
    server-side, which is what stops this app from recording consent to
    something other than what it displayed — the asymmetry with the onboarding
    wizard, which renders its own text and therefore has to prove what it showed.
    """
    base = (settings.ds_connector_url or "").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{base}/consent/my/shares",
                json={"offer_id": offer_id, "enabled": enabled},
                headers=credential.headers,
            )
    except httpx.HTTPError as exc:
        raise DataSharingUnavailable(f"Connector unreachable: {exc}") from exc

    if resp.status_code == 409:
        raise ValueError(
            "This offer is not consent-based — it is disclosed under a contract "
            "and cannot be toggled."
        )
    if resp.status_code >= 400:
        raise DataSharingUnavailable(
            f"Connector refused the change ({resp.status_code})"
        )
    return resp.json()


async def list_history(credential: SubjectCredential) -> list[dict[str, Any]]:
    """What has happened with this member's data, from their own record.

    Served by provenance and authenticated by the same credential, so it is the
    member's history rather than a view this app assembles. Absent provenance is
    not an error — the decisions still stand without it.
    """
    base = (settings.ds_provenance_url or "").rstrip("/")
    if not base:
        return []

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{base}/prov/my/events", headers=credential.headers
            )
    except httpx.HTTPError as exc:
        logger.warning("Provenance unreachable: %s", exc)
        return []

    if resp.status_code >= 400:
        logger.warning("Provenance answered %s", resp.status_code)
        return []

    body = resp.json()
    events = body.get("@graph", body) if isinstance(body, dict) else body
    return events if isinstance(events, list) else []
