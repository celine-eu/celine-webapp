"""Where a community's legal documents are, when the registry does not say.

A legal host serves every community's documents at one address per *slot*:
`<LEGAL_BASE_URL>/<community key>/<slot>/` always shows the slot's current version. So a
link the rec-registry leaves empty still resolves, and a new community needs no link
written anywhere. The rule, per link:

1. the community's own registry link, when it is set (an operator can always point one
   community elsewhere);
2. otherwise the legal host's slot address, when `LEGAL_BASE_URL` is set;
3. otherwise nothing: the frontend keeps its own fallback, exactly as before.

`LEGAL_BASE_URL` is empty by default, so a deployment without a legal host behaves as it
always has.
"""

from __future__ import annotations

from urllib.parse import quote

# The rec-registry's `community.links` key → the legal host's slot.
REGISTRY_LINK_SLOTS: dict[str, str] = {
    "privacy_policy": "privacy",
    "terms": "terms",
    "statute": "statute",
    "regulations": "regulations",
}


def slot_url(base_url: str | None, community_key: str | None, slot: str) -> str | None:
    """`<base>/<community>/<slot>/`, or None without a base or a community."""
    if not base_url or not community_key:
        return None
    return f"{base_url.rstrip('/')}/{quote(community_key, safe='')}/{slot}/"


def resolve_link(
    registry_value: object, base_url: str | None, community_key: str | None, registry_key: str
) -> str | None:
    """The link to show for one registry key, by the rule in this module's docstring."""
    explicit = str(registry_value).strip() if registry_value is not None else ""
    if explicit:
        return explicit
    return slot_url(base_url, community_key, REGISTRY_LINK_SLOTS[registry_key])
