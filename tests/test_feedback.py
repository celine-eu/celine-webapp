"""Participant feedback ownership and manager review workflow."""

import base64

PAYLOAD = {
    "rating": 4,
    "comment": "The consumption card is hard to understand",
    "context": {
        "page_url": "http://webapp.celine.localhost/",
        "page_title": "User dashboard",
        "page_path": "/",
        "locale": "it",
        "extra": {"community_key": "untrusted-rec"},
    },
    "screenshot": {
        "mime_type": "image/png",
        "data_base64": base64.b64encode(b"png-image").decode(),
    },
}


def manager_headers(make_token, community: str = "community-1") -> dict[str, str]:
    token = make_token(
        sub="manager-1",
        scope="community.read",
        organization={community: {"type": ["rec"], "groups": ["/managers"]}},
    )
    return {"x-auth-request-access-token": token}


def test_participant_feedback_is_filed_under_the_registry_rec_and_visible_to_its_manager(
    client, auth_headers, make_token
) -> None:
    created = client.post("/api/feedback", headers=auth_headers, json=PAYLOAD)
    assert created.status_code == 201
    feedback_id = created.json()["id"]

    response = client.get(
        "/api/feedback/manager/community-1", headers=manager_headers(make_token)
    )
    assert response.status_code == 200
    data = response.json()
    assert data["community_key"] == "community-1"
    assert data["counts"] == {"new": 1, "seen": 0, "resolved": 0}
    assert data["items"][0]["id"] == feedback_id
    assert data["items"][0]["extra"]["community_key"] == "community-1"
    assert data["items"][0]["has_screenshot"] is True

    screenshot = client.get(
        f"/api/feedback/manager/community-1/{feedback_id}/screenshot",
        headers=manager_headers(make_token),
    )
    assert screenshot.status_code == 200
    assert screenshot.headers["content-type"] == "image/png"
    assert screenshot.content == b"png-image"


def test_manager_cannot_read_feedback_from_another_rec(
    client, auth_headers, make_token
) -> None:
    assert client.post("/api/feedback", headers=auth_headers, json=PAYLOAD).status_code == 201
    response = client.get(
        "/api/feedback/manager/community-1",
        headers=manager_headers(make_token, "different-rec"),
    )
    assert response.status_code == 403


def test_manager_can_advance_user_feedback_to_resolved(
    client, auth_headers, make_token
) -> None:
    feedback_id = client.post("/api/feedback", headers=auth_headers, json=PAYLOAD).json()["id"]
    response = client.patch(
        f"/api/feedback/manager/community-1/{feedback_id}",
        headers=manager_headers(make_token),
        json={"status": "resolved"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "resolved"
    assert response.json()["seen_at"] is not None
    assert response.json()["resolved_at"] is not None

    backward = client.patch(
        f"/api/feedback/manager/community-1/{feedback_id}",
        headers=manager_headers(make_token),
        json={"status": "seen"},
    )
    assert backward.status_code == 409


# ─── Two levels: platform-admin (realm role) vs the REC's own groups ─────────
#
# The claim shapes below are those of real `oauth2_proxy` access tokens from a converged
# local realm: the platform level is the realm role in `realm_access.roles`; organisation
# groups appear only under `organization.<alias>.groups`, with the same `/admins`-style
# path a retired realm group had. `tests/integration/test_real_tokens.py` repeats the
# decisive cases with tokens Keycloak itself issued.


def _get(client, make_token, community: str = "community-1", **claims):
    token = make_token(sub="caller-1", scope="community.read", **claims)
    return client.get(
        f"/api/feedback/manager/{community}",
        headers={"x-auth-request-access-token": token},
    )


def test_platform_admin_role_reaches_a_rec_it_is_not_a_member_of(client, make_token) -> None:
    response = _get(client, make_token, realm_access={"roles": ["platform-admin"]})
    assert response.status_code == 200
    assert response.json()["community_key"] == "community-1"


def test_platform_admin_still_needs_the_community_read_scope(client, make_token) -> None:
    token = make_token(sub="caller-1", scope="openid", realm_access={"roles": ["platform-admin"]})
    response = client.get(
        "/api/feedback/manager/community-1",
        headers={"x-auth-request-access-token": token},
    )
    assert response.status_code == 403


def test_an_organisation_admin_is_not_a_platform_admin(client, make_token) -> None:
    org_admin = {
        "realm_access": {"roles": ["default-roles-celine", "offline_access", "uma_authorization"]},
        "organization": {"community-1": {"type": ["rec"], "groups": ["/admins"]}},
    }
    assert _get(client, make_token, "community-1", **org_admin).status_code == 200
    assert _get(client, make_token, "community-2", **org_admin).status_code == 403


def test_an_organisation_viewer_is_not_a_manager_of_its_own_rec(client, make_token) -> None:
    viewer = {"organization": {"community-1": {"type": ["rec"], "groups": ["/viewers"]}}}
    assert _get(client, make_token, **viewer).status_code == 403


def test_a_retired_realm_admins_group_grants_nothing(client, make_token) -> None:
    """The old token shape of a realm `/admins` member: both `groups` forms, realm role `admin`."""
    legacy = {
        "groups": ["/admins", "admins"],
        "realm_access": {"roles": ["admin"]},
        "organization": {"community-2": {"type": ["rec"], "groups": ["/viewers"]}},
    }
    assert _get(client, make_token, **legacy).status_code == 403


def test_platform_admin_counts_only_as_a_realm_role(client, make_token) -> None:
    """The name elsewhere in the token is not the role: not in `groups`, not a client role,
    not a top-level `roles` claim, not an organisation group."""
    for claims in (
        {"groups": ["platform-admin", "/platform-admin"]},
        {"roles": ["platform-admin"]},
        {"resource_access": {"oauth2_proxy": {"roles": ["platform-admin"]}}},
        {"organization": {"community-2": {"type": ["rec"], "groups": ["/platform-admin"]}}},
        {"realm_access": {"roles": "platform-admin"}},
    ):
        assert _get(client, make_token, **claims).status_code == 403, claims


def test_an_admins_group_in_another_organisation_does_not_reach_this_rec(
    client, make_token
) -> None:
    other = {
        "organization": {
            "community-2": {"type": ["rec"], "groups": ["/admins"]},
            "community-1": {"type": ["rec"], "groups": ["/viewers"]},
        }
    }
    assert _get(client, make_token, "community-1", **other).status_code == 403
    assert _get(client, make_token, "community-2", **other).status_code == 200


def test_an_admins_group_in_a_non_rec_organisation_is_not_a_rec_manager(
    client, make_token
) -> None:
    dso = {"organization": {"community-1": {"type": ["dso"], "groups": ["/admins"]}}}
    assert _get(client, make_token, **dso).status_code == 403
