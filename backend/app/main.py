"""FastAPI application entry point.

Creates the app, registers routes, manages lifecycle (DB init, DAS connections).
In production, serves the Next.js static build from /static.
"""

from __future__ import annotations

import asyncio
import logging
import pathlib
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Route modules
from app.api import (
    blacklist,
    dev,
    env_config,
    followers,
    locates,
    master,
    multipliers,
    queue,
    system,
    websocket,
)
from app.config import apply_env_text, get_config
from app.database import close_db, init_db
from app.engine.replication_engine import ReplicationEngine
from app.engine.scheduler import daily_restart_loop
from app.services.das_service import DASService
from app.services.log_buffer import LogBufferHandler, log_buffer
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

# --- Singletons (created once at startup) ---
_das_service = DASService()
_notifier = NotificationService()
_engine = ReplicationEngine(_das_service, _notifier)


async def _log_broadcast_loop() -> None:
    """Periodically drain new log entries and broadcast them via WebSocket."""
    last_seq = log_buffer.latest_seq
    while True:
        await asyncio.sleep(2)
        new = log_buffer.get_new_entries(since_seq=last_seq)
        if new and _notifier.client_count > 0:
            last_seq = new[-1]["seq"]
            await _notifier.broadcast("log_entries", {"entries": new})


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: init DB on startup, stop services on shutdown."""
    config = get_config()

    # Configure logging
    log_level = getattr(logging, config.log_level.upper(), logging.INFO)
    log_fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=log_level, format=log_fmt)

    # Attach in-memory log buffer handler to root logger
    buf_handler = LogBufferHandler(log_buffer)
    buf_handler.setFormatter(logging.Formatter(log_fmt))
    logging.getLogger().addHandler(buf_handler)

    # Persist logs to disk (new file per run)
    log_dir = pathlib.Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"app_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter(log_fmt))
    logging.getLogger().addHandler(file_handler)

    # Initialize database
    await init_db()
    logger.info("Database initialized at %s", config.db_path)

    # Load persisted env vars from DB and apply to running process
    try:
        from sqlalchemy import select as sa_select

        from app.database import get_session_factory
        from app.models.env_config import EnvConfig

        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(sa_select(EnvConfig).where(EnvConfig.id == 1))
            env_row = result.scalar_one_or_none()
            if env_row and env_row.content.strip():
                applied = apply_env_text(env_row.content)
                logger.info("Loaded %d env vars from DB", len(applied))
    except Exception as exc:
        logger.warning("Could not load env vars from DB: %s", exc)

    # Re-read config after env vars are applied
    config = get_config()

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

    # Start background tasks
    log_task = asyncio.create_task(_log_broadcast_loop())
    restart_task = asyncio.create_task(daily_restart_loop(_das_service, _engine))

    yield

    # Shutdown
    logger.info("Shutting down...")
    restart_task.cancel()
    log_task.cancel()
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
    app.include_router(env_config.router)
    app.include_router(master.router)
    app.include_router(followers.router)
    app.include_router(blacklist.router)
    app.include_router(multipliers.router)
    app.include_router(locates.router)
    app.include_router(queue.router)
    app.include_router(system.router)
    app.include_router(websocket.router)
    app.include_router(dev.router)

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
