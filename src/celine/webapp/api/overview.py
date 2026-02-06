"""Overview and dashboard routes."""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter

from celine.webapp.api.deps import UserDep, DbDep, ensure_user_exists
from celine.webapp.api.schemas import OverviewResponse


router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/overview", response_model=OverviewResponse)
async def overview(
    user: UserDep,
    db: DbDep,
) -> OverviewResponse:
    """Get overview dashboard data."""
    await ensure_user_exists(user, db)
    
    # Stubbed KPIs until Digital Twin integration exists
    user_has_prod = False  # could be inferred from DT later
    user_consumption = 42.3
    user_production = 18.7 if user_has_prod else None
    user_self = 12.1 if user_has_prod else None
    user_rate = (
        (user_self / user_consumption)
        if (user_self is not None and user_consumption > 0)
        else None
    )
    
    rec_prod = 1200.0
    rec_cons = 1650.0
    rec_self = 980.0
    rec_rate = rec_self / rec_cons if rec_cons > 0 else 0.0
    
    # Generate trend data for last 7 days
    base = datetime.now(timezone.utc).date()
    trend = []
    for d in range(7):
        day = (base - timedelta(days=(6 - d))).isoformat()
        trend.append(
            {
                "date": day,
                "production_kwh": 160.0 + d * 5.0,
                "consumption_kwh": 220.0 + d * 3.0,
                "self_consumption_kwh": 130.0 + d * 4.0,
            }
        )
    
    return OverviewResponse(
        period="Last 7 days",
        user={
            "production_kwh": user_production,
            "consumption_kwh": user_consumption,
            "self_consumption_kwh": user_self,
            "self_consumption_rate": user_rate,
        },
        rec={
            "production_kwh": rec_prod,
            "consumption_kwh": rec_cons,
            "self_consumption_kwh": rec_self,
            "self_consumption_rate": rec_rate,
        },
        trend=trend,
    )
