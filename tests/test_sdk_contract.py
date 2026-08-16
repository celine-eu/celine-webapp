"""What `celine-sdk` actually returns, checked against the installed package.

`tests/fakes.py` reproduces the *shape* of the SDK's responses so the fan-out tests can
run without the four upstream services. Nothing made those fakes answerable to the real
models, and ADR-0001 named that as the standing cost of a hermetic suite.

**It cost something within a day of being written.** A fake was given a
`membership.member.delivery_points` attribute carrying a `meter_id` string. Both were
invented. The real `UserMemberSummarySchema` has neither, so a branch in
`api/overview.py` that read them had never once executed — and the fake made it look like
a live bug, complete with a reproduction.

These tests close that specific gap. They assert the SDK models the routes actually
navigate, so a fake that drifts from the package is caught here rather than believed.

They import from the installed `celine-sdk` and reach no network, so they stay hermetic.
**They verify the models, not the service** — an upstream deployment can still serve
something its own SDK does not describe, and nothing here would notice.

Extend this file whenever a fake grows a new attribute.
"""

from __future__ import annotations

import inspect

import pytest

from celine.sdk.openapi.dt.models import (
    UserAssetSchema,
    UserCommunitySummarySchema,
    UserMemberSummarySchema,
    UserMembershipSchema,
)


# ─── The attributes api/overview.py navigates ────────────────────────────────


def test_membership_exposes_community_and_member() -> None:
    """`participant.membership.community.key` and `.member.key` — the resolution path."""
    community = UserCommunitySummarySchema(key="c1", name="C")
    member = UserMemberSummarySchema(area="A", key="m1", name="N", role="r", status="s")
    membership = UserMembershipSchema(community=community, member=member)

    assert membership.community.key == "c1"
    assert membership.member.key == "m1"


def test_the_membership_member_carries_no_delivery_points() -> None:
    """The reason a block in `api/overview.py` was removed rather than corrected.

    `membership.member` is a *summary*, not a detail. `UserMemberDetailSchema` does carry
    `delivery_points`, which is what makes the mistake easy — but it is not what the
    membership holds, so `getattr(member, "delivery_points", None)` returned `None` on
    every request the service has ever served.

    If this test ever fails, the SDK has changed and the removed block deserves a second
    look — but note that `DeliveryPointSchema` has no `meter_id` either.
    """
    member = UserMemberSummarySchema(area="A", key="m1", name="N", role="r", status="s")

    assert not hasattr(member, "delivery_points")
    assert getattr(member, "delivery_points", None) is None
    # attrs models expose extras through __getitem__, not attribute access, so there is
    # no dynamic fallback that could make the attribute appear at runtime.
    assert not hasattr(type(member), "__getattr__")


def test_membership_counts_delivery_points_but_does_not_list_them() -> None:
    """`delivery_points_count` is an int, and is the only delivery-point data here."""
    community = UserCommunitySummarySchema(key="c1", name="C")
    member = UserMemberSummarySchema(area="A", key="m1", name="N", role="r", status="s")
    membership = UserMembershipSchema(community=community, member=member)

    assert "delivery_points_count" in membership.to_dict()
    assert "delivery_points" not in membership.to_dict()


def test_delivery_points_carry_no_meter_id_anywhere_in_the_dt_model() -> None:
    """Even the detail schema would not have supplied the field that was being read."""
    from celine.sdk.openapi.dt.models import DeliveryPointSchema

    fields = set(inspect.signature(DeliveryPointSchema.__init__).parameters)

    assert "meter_id" not in fields
    assert "id" in fields


def test_assets_expose_the_fields_the_overview_reads() -> None:
    """`sensor_id`, `key`, `name` and `device` — and `sensor_id` is optional."""
    asset = UserAssetSchema(asset_type="meter", key="a1", name="Home meter")

    assert hasattr(asset, "sensor_id")
    assert hasattr(asset, "device")
    assert asset.key == "a1"
    assert asset.name == "Home meter"


def test_an_asset_without_a_sensor_id_is_representable() -> None:
    """The overview drops such assets, so the SDK must permit them."""
    asset = UserAssetSchema(asset_type="meter", key="a1", name="No sensor")

    assert not asset.sensor_id


# ─── The value-fetcher result shape every fan-out depends on ─────────────────


def test_fetch_results_expose_count_and_items_with_to_dict() -> None:
    """`FakeResult` and `FakeRow` model this; every fan-out route reads it.

    The routes call `res.count`, iterate `res.items` and call `.to_dict()` on each — so
    all three have to exist on the real result.
    """
    from celine.sdk.openapi.dt.models import FetchResultSchema

    fields = set(inspect.signature(FetchResultSchema.__init__).parameters)

    assert "count" in fields
    assert "items" in fields
    assert hasattr(FetchResultSchema, "to_dict")


@pytest.mark.parametrize(
    "name",
    ["profile", "assets", "fetch_values"],
)
def test_the_participant_client_still_has_the_methods_the_fakes_stand_in_for(
    name: str,
) -> None:
    """`FakeParticipants` substitutes these three. A rename would silently orphan it."""
    from celine.sdk.dt.participant import ParticipantClient

    assert callable(getattr(ParticipantClient, name, None))


def test_fetch_values_still_takes_participant_id_fetcher_id_and_payload() -> None:
    """The fakes assert on these argument names, so a rename must fail here first."""
    from celine.sdk.dt.participant import ParticipantClient

    params = set(inspect.signature(ParticipantClient.fetch_values).parameters)

    assert {"participant_id", "fetcher_id", "payload"} <= params
