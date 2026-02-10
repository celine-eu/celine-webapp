# celine/webapp/api/overview.py
"""Overview and dashboard routes."""
import logging
from datetime import datetime, timedelta, timezone

from celine.sdk.dt.community import DTApiError
from fastapi import APIRouter

from celine.webapp.api.deps import DbDep, DTDep, UserDep, ensure_user_exists
from celine.webapp.api.schemas import OverviewResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/overview", response_model=OverviewResponse)
async def overview(
    user: UserDep,
    db: DbDep,
    dt: DTDep,
) -> OverviewResponse:
    """Get overview dashboard data from the Digital Twin."""
    db_user = await ensure_user_exists(user, db)

    # Resolve participant's community.
    # The participant DT exposes the community membership as a value fetcher.
    participant_id = user.sub
    community_id: str | None = None

    try:
        participant_info = await dt.participants.info(participant_id)

        print("participant_info", participant_info)

        # Try to get community membership from a value fetcher
        try:
            membership = await dt.participants.get_value(
                participant_id,
                "communities",
            )
            items = membership.get("items", [])
            if items:
                community_id = items[0].get("community_id")
        except DTApiError:
            logger.debug(
                "No 'communities' fetcher for participant %s, "
                "checking profile fallback",
                participant_id,
            )
            # Fallback: community_id might be in the profile
            try:
                profile = await dt.participants.profile(participant_id)
                community_id = profile.get("community_id")
            except DTApiError:
                pass
    except DTApiError as exc:
        logger.warning("Failed to resolve participant %s: %s", participant_id, exc)

    # Fetch community energy balance
    user_data: dict = {
        "production_kwh": None,
        "consumption_kwh": None,
        "self_consumption_kwh": None,
        "self_consumption_rate": None,
    }
    rec_data: dict = {
        "production_kwh": None,
        "consumption_kwh": None,
        "self_consumption_kwh": None,
        "self_consumption_rate": None,
    }
    trend: list[dict] = []

    if community_id:
        try:
            balance = await dt.communities.energy_balance(community_id)

            # Community-level KPIs
            rec_prod = balance.get("production_kwh", 0.0)
            rec_cons = balance.get("consumption_kwh", 0.0)
            rec_self = balance.get("self_consumption_kwh", 0.0)
            rec_data = {
                "production_kwh": rec_prod,
                "consumption_kwh": rec_cons,
                "self_consumption_kwh": rec_self,
                "self_consumption_rate": (rec_self / rec_cons if rec_cons > 0 else 0.0),
            }

            # Per-user KPIs (if present in balance)
            user_balance = balance.get("participant", {})
            if user_balance:
                u_cons = user_balance.get("consumption_kwh", 0.0)
                u_prod = user_balance.get("production_kwh")
                u_self = user_balance.get("self_consumption_kwh")
                user_data = {
                    "production_kwh": u_prod,
                    "consumption_kwh": u_cons,
                    "self_consumption_kwh": u_self,
                    "self_consumption_rate": (
                        u_self / u_cons if u_self and u_cons and u_cons > 0 else None
                    ),
                }

            # Trend data (if present in balance)
            trend = balance.get("trend", [])

        except DTApiError as exc:
            logger.warning(
                "Failed to fetch energy balance for community %s: %s",
                community_id,
                exc,
            )

    # Fallback trend if DT didn't provide one
    if not trend:
        base = datetime.now(timezone.utc).date()
        for d in range(7):
            day = (base - timedelta(days=(6 - d))).isoformat()
            trend.append(
                {
                    "date": day,
                    "production_kwh": None,
                    "consumption_kwh": None,
                    "self_consumption_kwh": None,
                }
            )

    return OverviewResponse(
        period="Last 7 days",
        user=user_data,
        rec=rec_data,
        trend=trend,
    )
