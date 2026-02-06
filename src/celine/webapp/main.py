"""Main FastAPI application with async support."""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from celine.webapp.settings import settings
from celine.webapp.db import init_db
from celine.webapp.routes import create_api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup: Initialize database
    await init_db()
    yield
    # Shutdown: cleanup if needed


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="CELINE Webapp API",
        description="Renewable Energy Community Participant Webapp Backend",
        version="0.1.0",
        lifespan=lifespan,
        # OpenAPI documentation
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include API routes
    api_router = create_api_router()
    app.include_router(api_router)
    
    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "celine.webapp.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
