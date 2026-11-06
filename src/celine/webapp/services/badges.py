"""Badge catalogues: the legacy points badges and the fair-gamification ones."""

from __future__ import annotations

from typing import Any

#: Legacy (points variant). Kept for the existing routes and stored rows.
BADGES: dict[str, dict] = {
    "first-shift": {"icon": "zap", "min_actions": 1},
    "peak-saver": {"icon": "sun", "min_actions": 5},
    "solar-champion": {"icon": "leaf", "min_points": 500},
    "streak-3": {"icon": "trending-up", "streak_days": 3},
}

#: Fair variant (demo3 spec 2026-10-07 §4.5, design 2026-10-09 amendment 12).
FAIR_BADGES: dict[str, dict] = {
    "first-valid-week": {"icon": "calendar"},
    "first-kept": {"icon": "zap"},
    "four-at-max": {"icon": "sun"},
    "on-the-rise": {"icon": "trending-up"},
}

ALL_BADGE_ICONS: dict[str, str] = {**{k: v["icon"] for k, v in BADGES.items()}, **{k: v["icon"] for k, v in FAIR_BADGES.items()}}


def fair_badge_ids(weekly_history: list[dict[str, Any]], outcomes: list[dict[str, Any]]) -> set[str]:
    """Badges a member has unlocked under the fair variant.

    Args:
        weekly_history: ``rec_fair_weekly_scores`` rows of the member (any order).
        outcomes: ``rec_fair_commitment_outcomes`` rows of the member.

    Returns:
        The unlocked badge ids: first valid week, first kept commitment, four weeks at
        Level 100, Growth above 75 in two weeks.
    """
    unlocked: set[str] = set()
    if any(bool(w.get("is_valid_week")) for w in weekly_history):
        unlocked.add("first-valid-week")
    if any(bool(o.get("is_kept")) for o in outcomes):
        unlocked.add("first-kept")
    if sum(1 for w in weekly_history if (w.get("level_points") or 0) >= 100) >= 4:
        unlocked.add("four-at-max")
    if sum(1 for w in weekly_history if (w.get("growth_points") or 0) >= 75) >= 2:
        unlocked.add("on-the-rise")
    return unlocked
