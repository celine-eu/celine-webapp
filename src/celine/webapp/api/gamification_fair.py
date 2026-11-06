# celine/webapp/api/gamification_fair.py
"""`GET /api/gamification/fair` — the weekly Level / Growth / Actions boards.

Spec: demo3 docs/superpowers/specs/2026-10-07-gamification-equa-concept.md (design
2026-10-09). The pipeline computes everything (rec_fair_* gold tables); this route only
composes four Digital Twin fetchers into one response and derives the personal level
ladder (Σ weekly points / fair_points_per_level) and the fair badges.

Explanations are codes plus numbers: the webapp renders "sei qui perché…" from
`*_reason` and `params`; no copy is produced here.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from celine.webapp.api.deps import DbDep, DTDep, UserDep
from celine.webapp.api.schemas import (
    BadgeItem,
    BoardStanding,
    FairSeason,
    FairWeeklyScore,
    GamificationFairResponse,
)
from celine.webapp.db.models import UserBadge
from celine.webapp.services.badges import ALL_BADGE_ICONS, fair_badge_ids
from celine.webapp.services.log_safety import failure
from celine.webapp.services.participant_device import resolve_device_id
from celine.webapp.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["gamification"])

#: Weekly cap of Actions points — mirrors flexibility_config.yaml `fair.actions_weekly_cap`.
FAIR_ACTIONS_WEEKLY_CAP = 20

_BOARDS: tuple[tuple[str, str, str, str, str], ...] = (
    # (board, score column, rank column, total column, weeks column)
    ("virtuosi", "virtuosi_score", "virtuosi_rank", "total_ranked_virtuosi", "weeks_with_level"),
    ("in_crescita", "growth_score", "growth_rank", "total_ranked_growth", "weeks_with_growth"),
    ("generale", "general_score", "general_rank", "total_ranked_general", "weeks_with_both"),
)

_STATUS_BY_RANK_REASON: dict[str, str] = {
    "ranked": "ranked",
    "min_weeks": "not_yet_ranked",
    "first_week": "not_yet_ranked",
    "silent": "silent",
    "quarantined": "quarantined",
    "not_in_app": "not_eligible",
    "category_not_ranked": "not_eligible",
}


def _int(value: Any) -> int | None:
    """Round a numeric cell to an int; None stays None."""
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _pct(value: Any) -> int | None:
    """A 0–1 ratio as a rounded percentage; None stays None."""
    return None if value is None else _int(float(value) * 100.0)


def fair_level(season_points: int, step: int) -> tuple[int, int]:
    """Level ladder on the season sum of weekly points: (level, next_level_at)."""
    step = max(1, step)
    level = max(1, season_points // step + 1)
    return level, level * step


def board_from_row(row: dict[str, Any], board: str) -> BoardStanding:
    """Map one rec_fair_season_boards row to the standing in ``board``."""
    _, score_col, rank_col, total_col, weeks_col = next(b for b in _BOARDS if b[0] == board)
    rank = _int(row.get(rank_col))
    rank_reason = str(row.get("rank_reason") or "ranked")
    reason = "ranked" if rank is not None else (rank_reason if rank_reason != "ranked" else "min_weeks_board")
    score = row.get(score_col)
    return BoardStanding(
        board=board,  # type: ignore[arg-type]
        score=None if score is None else float(score),
        rank=rank,
        total_ranked=_int(row.get(total_col)) or 0,
        weeks_counted=_int(row.get(weeks_col)) or 0,
        reason=reason,
        params={
            "valid": _int(row.get("valid_weeks")) or 0,
            "required": _int(row.get("required_weeks")) or 0,
        },
    )


def week_from_row(row: dict[str, Any]) -> FairWeeklyScore:
    """Map one rec_fair_weekly_scores row to the API shape (points rounded to integers)."""
    flags = ["F1_IMPORT_RISE"] if row.get("flag_import_rise") else []
    # The Level is judged on level_metric (the night share on cloudy days for PV members,
    # on all days otherwise): that is the number the explanation must show.
    group = str(row.get("ref_group_effective") or "")
    params: dict[str, float | int | str] = {"merged": 1 if group.startswith("all/") else 0}
    for key, value in (
        ("night_share_pct", _pct(row.get("level_metric") if row.get("level_metric") is not None else row.get("night_share"))),
        ("group_percentile", _int(row.get("level_pct"))),
        ("group_size", _int(row.get("ref_group_n"))),
        ("cloudy_days", _int(row.get("cloudy_valid_days"))),
        ("change_pct", _pct(row.get("growth_delta_adj"))),
        ("kept_count", _int(row.get("kept_count"))),
        ("surplus_hours", _int(row.get("surplus_hours"))),
    ):
        if value is not None:
            params[key] = value
    return FairWeeklyScore(
        week_start=str(row.get("week_start", ""))[:10],
        is_valid_week=bool(row.get("is_valid_week")),
        level_points=_int(row.get("level_points")),
        level_reason=str(row.get("level_reason") or "no_valid_week"),
        growth_points=_int(row.get("growth_points")),
        growth_reason=str(row.get("growth_reason") or "no_valid_week"),
        actions_points=_int(row.get("actions_points")) or 0,
        actions_reason=str(row.get("actions_reason") or "no_commitments"),
        kept_count=_int(row.get("kept_count")) or 0,
        surplus_hours=_int(row.get("surplus_hours")) or 0,
        weekly_points=_int(row.get("weekly_points")) or 0,
        flags=flags,
        params=params,
    )


def status_from(board_row: dict[str, Any] | None) -> tuple[str, str | None]:
    """Derive the member status (and its reason code) from the season board row."""
    if board_row is None:
        return "not_yet_ranked", "no_valid_week"
    reason = str(board_row.get("rank_reason") or "ranked")
    return _STATUS_BY_RANK_REASON.get(reason, "not_yet_ranked"), (None if reason == "ranked" else reason)


async def _fetch(dt: Any, participant_id: str, fetcher_id: str, device_id: str) -> list[dict[str, Any]]:
    """Rows of one participant fetcher; raises on failure (the caller decides)."""
    res = await dt.participants.fetch_values(
        participant_id=participant_id, fetcher_id=fetcher_id, payload={"device_id": device_id}
    )
    return [item.to_dict() for item in res.items] if res and res.count > 0 else []


@router.get("/gamification/fair", response_model=GamificationFairResponse)
async def gamification_fair(user: UserDep, db: DbDep, dt: DTDep) -> GamificationFairResponse:
    """Return the member's fair-gamification standing, weekly history and badges.

    Always answers 200: `status` says whether the member is ranked, waiting for valid
    weeks, silent, quarantined, not eligible, without a meter, or whether the twin could
    not be reached (`unavailable`).
    """
    step = settings.fair_points_per_level
    device_id = await resolve_device_id(dt, user.sub)
    if not device_id:
        return GamificationFairResponse(status="no_device", next_level_at=step)

    try:
        board_rows, week_rows, class_rows, outcome_rows = await asyncio.gather(
            _fetch(dt, user.sub, "rec_fair_season_board", device_id),
            _fetch(dt, user.sub, "rec_fair_weekly_scores", device_id),
            _fetch(dt, user.sub, "rec_fair_device_class", device_id),
            _fetch(dt, user.sub, "rec_fair_commitment_outcomes", device_id),
        )
    except Exception as exc:
        logger.warning("gamification/fair: twin fetch failed (%s)", failure(exc))
        return GamificationFairResponse(status="unavailable", next_level_at=step)

    board = board_rows[0] if board_rows else None
    status, status_reason = status_from(board)
    weeks = sorted((week_from_row(r) for r in week_rows), key=lambda w: w.week_start)
    season_points = _int(board.get("season_points")) if board else None
    if season_points is None:
        season_points = sum(w.weekly_points for w in weeks)
    level, next_level_at = fair_level(season_points, step)

    season = None
    boards: list[BoardStanding] = []
    if board is not None:
        season = FairSeason(
            start=str(board.get("season_start", ""))[:10],
            end=str(board.get("season_end", ""))[:10],
            elapsed_weeks=_int(board.get("elapsed_weeks")) or 0,
            valid_weeks=_int(board.get("valid_weeks")) or 0,
            required_weeks=_int(board.get("required_weeks")) or 0,
        )
        boards = [board_from_row(board, name) for name, *_ in _BOARDS]

    klass = class_rows[0] if class_rows else (board or {})
    category = klass.get("category") if klass.get("category") in ("household", "public_entity") else None
    pv_class = klass.get("pv_class") if klass.get("pv_class") in ("pv", "no_pv") else None
    group_size = _int(weeks[-1].params.get("group_size")) if weeks and "group_size" in weeks[-1].params else None

    unlocked = fair_badge_ids(week_rows, outcome_rows)
    async with db as session:
        rows = (await session.execute(select(UserBadge).where(UserBadge.user_id == user.sub))).scalars().all()
        existing = {row.badge_id for row in rows}
        for badge_id in sorted(unlocked - existing):
            session.add(UserBadge(user_id=user.sub, badge_id=badge_id))
        if unlocked - existing:
            await session.commit()
            rows = (await session.execute(select(UserBadge).where(UserBadge.user_id == user.sub))).scalars().all()
        badges = [
            BadgeItem(badge_id=row.badge_id, icon=ALL_BADGE_ICONS.get(row.badge_id, "zap"), earned_at=row.earned_at.isoformat())
            for row in rows
        ]

    return GamificationFairResponse(
        status=status,  # type: ignore[arg-type]
        status_reason=status_reason,
        season=season,
        category=category,  # type: ignore[arg-type]
        pv_class=pv_class,  # type: ignore[arg-type]
        reference_group_size=group_size,
        season_points=season_points,
        level=level,
        next_level_at=next_level_at,
        badges=badges,
        boards=boards,
        latest_week=weeks[-1] if weeks else None,
        weekly_history=weeks,
        actions={
            "points_per_kept": settings.fair_points_per_kept,
            "weekly_cap": FAIR_ACTIONS_WEEKLY_CAP,
            "kept_season": sum(1 for o in outcome_rows if o.get("is_kept")),
            "surplus_hours_season": sum(_int(o.get("surplus_hours_kept")) or 0 for o in outcome_rows),
        },
    )
