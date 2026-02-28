"""API package - route handlers."""

from celine.webapp.api.user import router as user_router
from celine.webapp.api.overview import router as overview_router
from celine.webapp.api.notifications import router as notifications_router
from celine.webapp.api.settings_routes import router as settings_routes_router
from celine.webapp.api.meta import router as meta_router

__all__ = [
    "user_router",
    "overview_router",
    "notifications_router",
    "settings_routes_router",
    "meta_router",
]
