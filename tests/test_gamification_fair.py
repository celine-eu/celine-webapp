"""Fair gamification variant (plan Phase 4): flag, schemas and the /api/gamification/fair route.

Spec: demo3 docs/superpowers/specs/2026-10-07-gamification-equa-concept.md (design 2026-10-09).
"""

from __future__ import annotations

from celine.webapp.settings import settings


class TestVariantFlag:
    def test_points_variant_is_the_default(self):
        """Until the flag flips at a season start, members see today's points."""
        assert settings.gamification_variant == "points"

    def test_fair_level_step_and_kept_points_defaults(self):
        """Mirrors flexibility_config.yaml `fair.points_per_level` / `fair.points_per_kept`."""
        assert settings.fair_points_per_level == 150
        assert settings.fair_points_per_kept == 5

    def test_me_advertises_the_variant(self):
        """`/api/me` carries the variant so the UI picks the panel without a second call."""
        from celine.webapp.api.schemas import MeResponse

        field = MeResponse.model_fields["gamification_variant"]
        assert field.default == "points"


# ─── Schemas ──────────────────────────────────────────────────────────────────


class TestSchemas:
    def test_fair_response_defaults_are_safe(self):
        from celine.webapp.api.schemas import GamificationFairResponse

        r = GamificationFairResponse(status="unavailable", next_level_at=150)
        assert r.variant == "fair" and r.season_points == 0 and r.level == 1
        assert r.boards == [] and r.weekly_history == [] and r.badges == []

    def test_board_standing_carries_reason_and_params(self):
        from celine.webapp.api.schemas import BoardStanding

        b = BoardStanding(board="generale", reason="min_weeks", params={"valid": 1, "required": 2})
        assert b.rank is None and b.total_ranked == 0 and b.params["required"] == 2


# ─── Route ───────────────────────────────────────────────────────────────────


def _board_row(**overrides) -> dict:
    row = {
        "device_id": "c2g-57CFA0F18", "season_start": "2026-09-01", "season_end": "2026-11-01",
        "category": "household", "pv_class": "no_pv", "ref_group_effective": "household/no_pv",
        "elapsed_weeks": 4, "valid_weeks": 4, "required_weeks": 2, "is_ranked": True, "rank_reason": "ranked",
        "weeks_with_level": 4, "weeks_with_growth": 3, "weeks_with_both": 3,
        "mean_level": 81.25, "mean_growth": 66.7, "actions_sum": 15, "weeks_at_100": 1, "season_points": 320,
        "virtuosi_score": 81.25, "virtuosi_rank": 2, "growth_score": 66.7, "growth_rank": 1,
        "general_score": 88.975, "general_rank": 1, "total_ranked_virtuosi": 11, "total_ranked_growth": 9,
        "total_ranked_general": 9, "last_valid_week_start": "2026-09-28",
    }
    row.update(overrides)
    return row


def _week_row(**overrides) -> dict:
    row = {
        "device_id": "c2g-57CFA0F18", "week_start": "2026-09-28", "season_start": "2026-09-01", "is_valid_week": True,
        "is_rankable": True, "pv_class": "no_pv", "category": "household", "ref_group_effective": "household/no_pv",
        "ref_group_n": 12, "night_share": 0.284, "cloudy_valid_days": 2, "level_metric": 0.284, "level_source": "all_days",
        "level_pct": 72.7, "level_points": 90.9, "level_reason": "all_days", "growth_n": 2, "growth_delta": -0.12,
        "growth_delta_adj": -0.08, "growth_pct": 60.0, "growth_points": 60.0, "growth_reason": "improving",
        "kept_count": 1, "surplus_hours": 0, "actions_points": 5, "actions_reason": "kept", "weekly_points": 155.9,
        "import_rise_pct": 0.05, "flag_import_rise": False,
    }
    row.update(overrides)
    return row


def _class_row(**overrides) -> dict:
    row = {"device_id": "c2g-57CFA0F18", "week_start": "2026-09-28", "pv_class": "no_pv", "pv_source": "none",
           "category": "household", "ref_group": "household/no_pv", "is_in_app": True, "is_quarantined": False,
           "is_silent": False, "is_rankable": True, "battery_declared": False, "last_reading_at": "2026-10-04"}
    row.update(overrides)
    return row


class TestFairRoute:
    def test_ranked_member_gets_three_boards_level_and_explanations(self, client, auth_headers, fake_dt, monkeypatch):
        monkeypatch.setattr(settings, "fair_points_per_level", 150)
        fake_dt.participants.values["rec_fair_season_board"] = [_board_row()]
        fake_dt.participants.values["rec_fair_weekly_scores"] = [_week_row(), _week_row(week_start="2026-09-21", weekly_points=100.0)]
        fake_dt.participants.values["rec_fair_device_class"] = [_class_row()]
        fake_dt.participants.values["rec_fair_commitment_outcomes"] = [
            {"commitment_id": "c1", "period_start": "2026-09-30T13:00:00+02:00", "period_end": "2026-09-30T14:00:00+02:00",
             "matched": True, "is_kept": True, "points": 5, "surplus_points": 0, "reason": "kept"}
        ]

        body = client.get("/api/gamification/fair", headers=auth_headers).json()

        assert body["status"] == "ranked" and body["variant"] == "fair"
        assert body["category"] == "household" and body["pv_class"] == "no_pv" and body["reference_group_size"] == 12
        assert body["season"] == {"start": "2026-09-01", "end": "2026-11-01", "elapsed_weeks": 4, "valid_weeks": 4, "required_weeks": 2}
        assert body["season_points"] == 320 and body["level"] == 3 and body["next_level_at"] == 450
        boards = {b["board"]: b for b in body["boards"]}
        assert set(boards) == {"virtuosi", "in_crescita", "generale"}
        assert boards["generale"]["rank"] == 1 and boards["generale"]["total_ranked"] == 9 and boards["generale"]["reason"] == "ranked"
        assert boards["virtuosi"]["rank"] == 2 and boards["virtuosi"]["score"] == 81.25 and boards["virtuosi"]["weeks_counted"] == 4
        latest = body["latest_week"]
        assert latest["week_start"] == "2026-09-28" and latest["level_points"] == 91 and latest["level_reason"] == "all_days"
        assert latest["params"]["night_share_pct"] == 28 and latest["params"]["group_percentile"] == 73 and latest["params"]["group_size"] == 12
        assert latest["growth_reason"] == "improving" and latest["params"]["change_pct"] == -8
        assert latest["actions_points"] == 5 and latest["kept_count"] == 1
        assert [w["week_start"] for w in body["weekly_history"]] == ["2026-09-21", "2026-09-28"]  # oldest first for the chart
        assert body["actions"] == {"points_per_kept": 5, "weekly_cap": 20, "kept_season": 1, "surplus_hours_season": 0}

    def test_not_yet_ranked_shows_progress_towards_the_requirement(self, client, auth_headers, fake_dt):
        fake_dt.participants.values["rec_fair_season_board"] = [
            _board_row(is_ranked=False, rank_reason="min_weeks", valid_weeks=1, required_weeks=2,
                       virtuosi_rank=None, growth_rank=None, general_rank=None, virtuosi_score=None, growth_score=None, general_score=None)
        ]
        fake_dt.participants.values["rec_fair_device_class"] = [_class_row()]

        body = client.get("/api/gamification/fair", headers=auth_headers).json()

        assert body["status"] == "not_yet_ranked" and body["status_reason"] == "min_weeks"
        for b in body["boards"]:
            assert b["rank"] is None and b["reason"] == "min_weeks" and b["params"] == {"valid": 1, "required": 2}

    def test_no_rows_at_all_is_not_yet_ranked_without_boards(self, client, auth_headers, fake_dt):
        body = client.get("/api/gamification/fair", headers=auth_headers).json()

        assert body["status"] == "not_yet_ranked" and body["status_reason"] == "no_valid_week"
        assert body["boards"] == [] and body["season"] is None and body["latest_week"] is None

    def test_silent_and_quarantined_devices_get_their_status(self, client, auth_headers, fake_dt):
        fake_dt.participants.values["rec_fair_season_board"] = [_board_row(is_ranked=False, rank_reason="silent")]
        assert client.get("/api/gamification/fair", headers=auth_headers).json()["status"] == "silent"
        fake_dt.participants.values["rec_fair_season_board"] = [_board_row(is_ranked=False, rank_reason="quarantined")]
        assert client.get("/api/gamification/fair", headers=auth_headers).json()["status"] == "quarantined"
        fake_dt.participants.values["rec_fair_season_board"] = [_board_row(is_ranked=False, rank_reason="category_not_ranked")]
        assert client.get("/api/gamification/fair", headers=auth_headers).json()["status"] == "not_eligible"

    def test_twin_failure_is_unavailable_with_200(self, client, auth_headers, fake_dt):
        fake_dt.participants.value_errors["rec_fair_season_board"] = RuntimeError("twin down")

        resp = client.get("/api/gamification/fair", headers=auth_headers)

        assert resp.status_code == 200 and resp.json()["status"] == "unavailable"

    def test_legacy_route_is_unchanged(self, client, auth_headers, fake_dt):
        body = client.get("/api/gamification", headers=auth_headers).json()
        assert "total_points" in body and "variant" not in body

    def test_first_valid_week_badge_is_awarded_and_persisted(self, client, auth_headers, fake_dt):
        fake_dt.participants.values["rec_fair_season_board"] = [_board_row()]
        fake_dt.participants.values["rec_fair_weekly_scores"] = [_week_row()]
        fake_dt.participants.values["rec_fair_commitment_outcomes"] = [
            {"commitment_id": "c1", "period_start": "2026-09-30T13:00:00+02:00", "period_end": "2026-09-30T14:00:00+02:00",
             "matched": True, "is_kept": True, "points": 5, "surplus_points": 0, "reason": "kept"}
        ]
        first = client.get("/api/gamification/fair", headers=auth_headers).json()
        second = client.get("/api/gamification/fair", headers=auth_headers).json()
        ids = sorted(b["badge_id"] for b in first["badges"])
        assert ids == ["first-kept", "first-valid-week"]
        assert sorted(b["badge_id"] for b in second["badges"]) == ids  # not duplicated


# ─── Suggestions under the fair variant (Task 4.4) ───────────────────────────


class _FakeSuggestion:
    """Mirrors the SDK suggestion model surface the route uses: `.id` and `.model_dump()`."""

    def __init__(self, suggestion_id: str, reward_points: int) -> None:
        self.id = suggestion_id
        self._data = {
            "id": suggestion_id, "suggestion_type": "load_shift", "period_start": "2026-10-10T12:00:00+02:00",
            "period_end": "2026-10-10T15:00:00+02:00", "from_period": "evening", "clock_range": "12–15", "to_is_tomorrow": False,
            "to_period": "midday", "to_time": "12:00", "impact_kwh_estimated": 1.2, "reward_points": reward_points,
            "community_kwh": 3.0, "confidence": 0.7,
        }

    def model_dump(self) -> dict:
        return dict(self._data)


class TestSuggestionsUnderFairVariant:
    def test_fair_variant_promises_the_fixed_kept_points(self, client, auth_headers, fake_flexibility, monkeypatch):
        monkeypatch.setattr(settings, "gamification_variant", "fair")
        monkeypatch.setattr(settings, "fair_points_per_kept", 5)
        fake_flexibility.suggestions = [_FakeSuggestion("s1", 23), _FakeSuggestion("s2", 0)]

        body = client.get("/api/suggestions", headers=auth_headers).json()

        assert [s["reward_points"] for s in body] == [5, 5]

    def test_points_variant_keeps_the_estimate(self, client, auth_headers, fake_flexibility, monkeypatch):
        monkeypatch.setattr(settings, "gamification_variant", "points")
        fake_flexibility.suggestions = [_FakeSuggestion("s1", 23)]

        body = client.get("/api/suggestions", headers=auth_headers).json()

        assert body[0]["reward_points"] == 23


# ─── Review fixes 2026-10-09 ─────────────────────────────────────────────────


class TestExplanationNumbers:
    def test_pv_member_night_share_comes_from_the_level_metric_and_merge_is_flagged(self, client, auth_headers, fake_dt):
        """A PV member's Level is the cloudy-day share: the explanation must show that number, not the all-days share."""
        fake_dt.participants.values["rec_fair_season_board"] = [_board_row(pv_class="pv")]
        fake_dt.participants.values["rec_fair_weekly_scores"] = [
            _week_row(pv_class="pv", night_share=0.61, level_metric=0.284, level_source="cloudy_days", level_reason="cloudy_days",
                      ref_group_effective="all/pv", ref_group_n=7)
        ]
        fake_dt.participants.values["rec_fair_device_class"] = [_class_row(pv_class="pv")]

        latest = client.get("/api/gamification/fair", headers=auth_headers).json()["latest_week"]

        assert latest["params"]["night_share_pct"] == 28
        assert latest["params"]["merged"] == 1 and latest["params"]["group_size"] == 7

    def test_household_in_its_own_group_is_not_merged(self, client, auth_headers, fake_dt):
        fake_dt.participants.values["rec_fair_weekly_scores"] = [_week_row()]

        latest = client.get("/api/gamification/fair", headers=auth_headers).json()["latest_week"]

        assert latest["params"]["merged"] == 0 and latest["params"]["night_share_pct"] == 28
