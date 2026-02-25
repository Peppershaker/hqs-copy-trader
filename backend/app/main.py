"""FastAPI application entry point.

Creates the app, registers routes, manages lifecycle (DB init, DAS connections).
In production, serves the Next.js static build from /static.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

# Route modules
from app.api import (
    blacklist,
    followers,
    locates,
    master,
    multipliers,
    queue,
    system,
    websocket,
)
from app.config import get_config
from app.database import close_db, init_db
from app.engine.replication_engine import ReplicationEngine
from app.services.audit_service import AuditService
from app.services.das_service import DASService
from app.services.notification_service import NotificationService
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

# --- Singletons (created once at startup) ---
_das_service = DASService()
_notifier = NotificationService()
_audit = AuditService()
_engine = ReplicationEngine(_das_service, _notifier, _audit)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: init DB on startup, stop services on shutdown."""
    config = get_config()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Initialize database
    await init_db()
    logger.info("Database initialized at %s", config.db_path)

    # Inject dependencies into route modules
    locates.set_engine_getter(lambda: _engine)
    system.set_service_getters(lambda: _das_service, lambda: _engine)
    websocket.set_ws_dependencies(lambda: _notifier, lambda: _engine)
    queue.set_queue_engine_getter(lambda: _engine)

    logger.info(
        "DAS Copy Trader backend ready on http://%s:%s",
        config.app_host,
        config.app_port,
    )

    yield

    # Shutdown
    logger.info("Shutting down...")
    await _engine.stop()
    await _das_service.stop()
    await close_db()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    config = get_config()

    app = FastAPI(
        title="DAS Copy Trader",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS (needed for dev mode when frontend runs on different port)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routes
    app.include_router(master.router)
    app.include_router(followers.router)
    app.include_router(blacklist.router)
    app.include_router(multipliers.router)
    app.include_router(locates.router)
    app.include_router(queue.router)
    app.include_router(system.router)
    app.include_router(websocket.router)

    # Serve static frontend (production)
    static_dir = config.resolved_static_dir
    if static_dir:
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
        logger.info("Serving frontend from %s", static_dir)

    return app


# For uvicorn: `uvicorn app.main:app`
app = create_app()


if __name__ == "__main__":
    import uvicorn

    config = get_config()
    uvicorn.run(
        "app.main:app",
        host=config.app_host,
        port=config.app_port,
        reload=False,
        log_level=config.log_level.lower(),
    )
