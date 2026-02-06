"""Main routes module - combines all API routers."""
from fastapi import APIRouter

from celine.webapp.api import user, overview, notifications, settings_routes


def create_api_router() -> APIRouter:
    """Create and configure the main API router."""
    api_router = APIRouter()
    
    # Include all route modules
    api_router.include_router(user.router)
    api_router.include_router(overview.router)
    api_router.include_router(notifications.router)
    api_router.include_router(settings_routes.router)
    
    return api_router
