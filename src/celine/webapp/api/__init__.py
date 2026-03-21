"""API package - route handlers."""

from celine.webapp.api.user import router as user_router
from celine.webapp.api.overview import router as overview_router
from celine.webapp.api.notifications import router as notifications_router
from celine.webapp.api.settings_routes import router as settings_routes_router
from celine.webapp.api.meta import router as meta_router
from celine.webapp.api.weather import router as weather_router
from celine.webapp.api.forecast import router as forecast_router
from celine.webapp.api.suggestions import router as suggestions_router
from celine.webapp.api.gamification import router as gamification_router
from celine.webapp.api.community import router as community_router

__all__ = [
    "user_router",
    "overview_router",
    "notifications_router",
    "settings_routes_router",
    "meta_router",
    "weather_router",
    "forecast_router",
    "suggestions_router",
    "gamification_router",
    "community_router",
]
