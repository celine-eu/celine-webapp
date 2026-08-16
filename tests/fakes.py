"""Fakes for the four upstream services this repository fans out to.

Each fake stands where a `celine-sdk` client would, at the dependency-injection
boundary in `api/deps.py`. They are deliberately shallow: this repository owns no
upstream logic, only the composition of upstream responses, so a fake needs to reproduce
the *shape* the SDK returns and nothing about how the upstream computes it.

**These do not verify the contract.** They record what the SDK looked like on
2026-08-15. An SDK version bump can change the real shape and every test here will still
pass — see `.agents/knowledge/what-this-repository-depends-on.md`, which names that as
this repository's standing risk.

The shape the value-fetcher endpoints return is uniform across DT and flexibility: a
result with `.count` and `.items`, each item exposing `.to_dict()`.
"""

from __future__ import annotations

from typing import Any


# ─── Shared response shapes ──────────────────────────────────────────────────


class FakeRow:
    """One row of a value-fetcher result."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


class FakeResult:
    """A value-fetcher result: `.count` and `.items`."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        rows = rows or []
        self.count = len(rows)
        self.items = [FakeRow(r) for r in rows]


class FakeAsset:
    """One participant asset, as `dt.participants.assets()` returns it."""

    def __init__(
        self,
        sensor_id: str | None = "c2g-57CFA0F18",
        key: str = "asset-1",
        name: str = "Home meter",
        device: dict[str, Any] | None = None,
    ) -> None:
        self.sensor_id = sensor_id
        self.key = key
        self.name = name
        self.device = FakeRow(device) if device is not None else None


class FakeAssets:
    def __init__(self, items: list[FakeAsset] | None = None) -> None:
        self.items = items if items is not None else [FakeAsset()]


_DEFAULT = object()
"""Sentinel: `None` is a meaningful value for membership and member, so it cannot double
as "not supplied"."""


class _Named:
    def __init__(self, key: str) -> None:
        self.key = key


class FakeMember:
    """Mirrors `UserMemberSummarySchema`, which is what a membership actually holds.

    It carried a `delivery_points` attribute for a few hours on 2026-08-15. The real
    summary schema has no such field — only `UserMemberDetailSchema` does, and that is not
    what `membership.member` is — so the attribute made an unreachable branch in
    `api/overview.py` look like a live bug. **Do not add fields here without checking the
    model**; `tests/test_sdk_contract.py` is where that check belongs.
    """

    def __init__(self, key: Any = "member-1") -> None:
        self.key = key


class FakeMembership:
    """A membership. `member=None` is meaningful for the same reason as above."""

    def __init__(
        self,
        community_key: str = "community-1",
        member: Any = _DEFAULT,
    ) -> None:
        self.community = _Named(community_key)
        self.member = FakeMember() if member is _DEFAULT else member


class FakeParticipantProfile:
    """A participant profile.

    `membership` defaults to a populated one, but `None` must stay meaningful: a
    participant the twin knows about yet has not placed in a community is a state the
    overview route answers 404 for. Hence the sentinel rather than `None` as the default.
    """

    def __init__(self, membership: Any = _DEFAULT) -> None:
        self.membership = FakeMembership() if membership is _DEFAULT else membership


# ─── Digital Twin ────────────────────────────────────────────────────────────


class FakeParticipants:
    """`dt.participants` — profile, assets, and the value-fetcher endpoint.

    `fetch_values` dispatches on `fetcher_id`, which is how the routes distinguish
    meter readings from points from leaderboard rows. A test sets `values[fetcher_id]`
    to the rows it wants; an unset fetcher returns an empty result, which is the
    real-world case the routes are supposed to survive.
    """

    def __init__(self) -> None:
        self.profile_result: FakeParticipantProfile | None = FakeParticipantProfile()
        self.profile_error: Exception | None = None
        self.assets_result: FakeAssets | None = FakeAssets()
        self.assets_error: Exception | None = None
        self.values: dict[str, list[dict[str, Any]]] = {}
        self.value_errors: dict[str, Exception] = {}
        self.calls: list[dict[str, Any]] = []

    async def profile(self, participant_id: str) -> FakeParticipantProfile:
        self.calls.append({"method": "profile", "participant_id": participant_id})
        if self.profile_error is not None:
            raise self.profile_error
        return self.profile_result

    async def assets(self, participant_id: str) -> FakeAssets | None:
        self.calls.append({"method": "assets", "participant_id": participant_id})
        if self.assets_error is not None:
            raise self.assets_error
        return self.assets_result

    async def fetch_values(
        self,
        participant_id: str,
        fetcher_id: str,
        payload: dict[str, Any] | None = None,
    ) -> FakeResult:
        self.calls.append(
            {
                "method": "fetch_values",
                "participant_id": participant_id,
                "fetcher_id": fetcher_id,
                "payload": payload or {},
            }
        )
        if fetcher_id in self.value_errors:
            raise self.value_errors[fetcher_id]
        return FakeResult(self.values.get(fetcher_id, []))


class FakeCommunities:
    def __init__(self) -> None:
        self.values: dict[str, list[dict[str, Any]]] = {}
        self.value_errors: dict[str, Exception] = {}
        self.calls: list[dict[str, Any]] = []

    async def fetch_values(
        self,
        community_id: str,
        fetcher_id: str,
        payload: dict[str, Any] | None = None,
    ) -> FakeResult:
        self.calls.append(
            {
                "method": "fetch_values",
                "community_id": community_id,
                "fetcher_id": fetcher_id,
                "payload": payload or {},
            }
        )
        if fetcher_id in self.value_errors:
            raise self.value_errors[fetcher_id]
        return FakeResult(self.values.get(fetcher_id, []))


class FakeDTClient:
    """Stands in for `celine.sdk.dt.DTClient` — `../digital-twin`."""

    def __init__(self) -> None:
        self.participants = FakeParticipants()
        self.communities = FakeCommunities()


# ─── Flexibility ─────────────────────────────────────────────────────────────


class FakeFlexibilityClient:
    """Stands in for `celine.sdk.flexibility.FlexibilityClient` — `../flexibility-api`."""

    def __init__(self) -> None:
        self.commitments: list[Any] = []
        self.suggestions: list[Any] = []
        self.calls: list[str] = []

    async def list_commitments(self, *args: Any, **kwargs: Any) -> list[Any]:
        self.calls.append("list_commitments")
        return list(self.commitments)

    async def list_suggestions(self, *args: Any, **kwargs: Any) -> list[Any]:
        self.calls.append("list_suggestions")
        return list(self.suggestions)


# ─── Nudging ─────────────────────────────────────────────────────────────────


class FakePreferences:
    def __init__(
        self,
        max_per_day: int,
        channel_email: bool,
        email: str,
        enabled_notification_kinds: list[str],
    ) -> None:
        self.max_per_day = max_per_day
        self.channel_email = channel_email
        self.email = email
        self.enabled_notification_kinds = enabled_notification_kinds


class FakeNotification:
    """One notification, as the nudging client returns it.

    Attributes, not a dict: `list_notifications` in `api/notifications.py` reads
    `n.created_at.isoformat()`, so the timestamps must be real datetimes.
    """

    def __init__(
        self,
        id: str = "notif-1",
        created_at: Any = None,
        title: str = "Meter anomaly",
        body: str = "Your meter reported an unusual reading.",
        severity: str = "info",
        read_at: Any = None,
        deleted_at: Any = None,
    ) -> None:
        from datetime import datetime, timezone

        self.id = id
        self.created_at = created_at or datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
        self.title = title
        self.body = body
        self.severity = severity
        self.read_at = read_at
        self.deleted_at = deleted_at


class FakeNudgingClient:
    """Stands in for `celine.sdk.nudging.client.NudgingClient` — `../nudging-tool`.

    Preferences are held in memory so a PUT followed by a GET behaves the way the real
    service does; the settings route's round-trip is the thing worth exercising.

    `extr_event` is deliberately non-editable: the catalog distinguishes kinds a member
    may switch off from kinds they may not, and that flag has to survive the round-trip.
    """

    def __init__(self) -> None:
        self.max_per_day = 5
        self.channel_email = False
        self.email = ""
        self.enabled_notification_kinds = ["meter_anomaly", "price_up"]
        self.notifications: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []
        self.last_lang: str | None = None
        self.catalog: list[dict[str, Any]] = [
            {
                "kind": "meter_anomaly",
                "label": "Sensor and meter anomalies",
                "description": "Alerts for faulty devices.",
                "cadence": "At most once per day.",
                "enabled": True,
                "editable": True,
            },
            {
                "kind": "price_up",
                "label": "Price increase alerts",
                "description": "Alerts when prices rise.",
                "cadence": "At most once per day.",
                "enabled": True,
                "editable": True,
            },
            {
                "kind": "extr_event",
                "label": "Weather alerts",
                "description": "Relevant weather alerts for the community.",
                "cadence": "When a relevant alert is issued.",
                "enabled": True,
                "editable": False,
            },
        ]

    async def get_preferences(self, *, token: str | None = None) -> FakePreferences:
        return FakePreferences(
            self.max_per_day,
            self.channel_email,
            self.email,
            list(self.enabled_notification_kinds),
        )

    async def update_preferences(
        self,
        max_per_day: int,
        channel_email: bool | None = None,
        email: str | None = None,
        enabled_notification_kinds: list[str] | None = None,
        lang: str | None = None,
        *,
        token: str | None = None,
    ) -> FakePreferences:
        # `lang` is recorded rather than ignored: the settings route resolves it from the
        # query string or Accept-Language and forwards it, and a fake that swallowed it
        # would hide the route dropping it. It is also why this signature must stay in
        # step with the SDK — omitting the parameter here made the route answer 502.
        self.updates.append(
            {
                "max_per_day": max_per_day,
                "channel_email": channel_email,
                "email": email,
                "enabled_notification_kinds": enabled_notification_kinds,
                "lang": lang,
            }
        )
        self.last_lang = lang
        self.max_per_day = max_per_day
        if channel_email is not None:
            self.channel_email = channel_email
        if email is not None:
            self.email = email
        if enabled_notification_kinds is not None:
            self.enabled_notification_kinds = enabled_notification_kinds
            for item in self.catalog:
                item["enabled"] = item["kind"] in enabled_notification_kinds

        return FakePreferences(
            self.max_per_day,
            self.channel_email,
            self.email,
            list(self.enabled_notification_kinds),
        )

    async def get_preference_catalog(
        self, *, lang: str | None = None, token: str | None = None
    ) -> list[dict[str, Any]]:
        return [dict(item) for item in self.catalog]

    async def list_notifications(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        unread_only: bool = False,
        token: str | None = None,
    ) -> list[dict[str, Any]]:
        return list(self.notifications)


# ─── REC registry ────────────────────────────────────────────────────────────


class FakeCommunityDetail:
    def __init__(
        self,
        key: str = "community-1",
        name: str = "Test REC",
        description: str | None = "A community for tests",
        legal: dict[str, Any] | None = None,
        contact: dict[str, Any] | None = None,
        links: dict[str, Any] | None = None,
    ) -> None:
        self.key = key
        self.name = name
        self.description = description
        self.legal = legal or {}
        self.contact = contact or {}
        self.links = links or {}


class FakeRegistryClient:
    """Stands in for `celine.sdk.rec_registry.RecRegistryUserClient` — `../rec-registry`.

    Note that `GET /api/community` does **not** resolve its client through
    `get_registry_client`, so overriding that dependency does not reach it. See
    `.agents/knowledge/the-community-route-bypasses-injection.md`.
    """

    def __init__(self) -> None:
        self.community: FakeCommunityDetail | None = FakeCommunityDetail()
        self.error: Exception | None = None

    async def get_my_community(self) -> FakeCommunityDetail | None:
        if self.error is not None:
            raise self.error
        return self.community
