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
