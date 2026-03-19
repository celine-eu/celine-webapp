"""Main routes module - combines all API routers."""

from fastapi import APIRouter

from celine.webapp.api import (
    user_router,
    overview_router,
    notifications_router,
    settings_routes_router,
    meta_router,
    weather_router,
    forecast_router,
    suggestions_router,
    gamification_router,
)


def create_api_router() -> APIRouter:
    """Create and configure the main API router."""
    api_router = APIRouter()

    # Include all route modules
    api_router.include_router(user_router)
    api_router.include_router(overview_router)
    api_router.include_router(notifications_router)
    api_router.include_router(settings_routes_router)
    api_router.include_router(meta_router)
    api_router.include_router(weather_router)
    api_router.include_router(forecast_router)
    api_router.include_router(suggestions_router)
    api_router.include_router(gamification_router)

    return api_router
