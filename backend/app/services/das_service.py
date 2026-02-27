"""DAS client management service.

Manages the lifecycle of DASClient instances for master and follower accounts.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from das_bridge import DASClient
from das_bridge.config.settings import ConnectionConfig, GlobalConfig

logger = logging.getLogger(__name__)


class DASService:
    """Manages DASClient instances for master and follower accounts.

    This service is responsible for creating, starting, stopping, and tracking
    the connection state of all DAS clients.
    """

    def __init__(self) -> None:
        self._master_client: DASClient | None = None
        self._follower_clients: dict[str, DASClient] = {}
        self._master_config: dict[str, Any] | None = None
        self._follower_configs: dict[str, dict[str, Any]] = {}
        self._running = False

    @property
    def master_client(self) -> DASClient | None:
        return self._master_client

    @property
    def follower_clients(self) -> dict[str, DASClient]:
        return dict(self._follower_clients)

    def get_follower_client(self, follower_id: str) -> DASClient | None:
        """Get a single follower client by ID."""
        return self._follower_clients.get(follower_id)

    def get_connected_follower(self, follower_id: str) -> DASClient | None:
        """Get a follower client only if it is connected and running."""
        client = self._follower_clients.get(follower_id)
        if client and client.is_running:
            return client
        return None

    @property
    def is_running(self) -> bool:
        return self._running

    def _build_config(self, cfg: dict[str, Any]) -> GlobalConfig:
        """Build a GlobalConfig from a configuration dict."""
        conn = ConnectionConfig(
            host=cfg["host"],
            port=cfg["port"],
            username=cfg["username"],
            password=cfg["password"],
            account=cfg["account_id"],
            broker=cfg.get("broker", "default"),
            connection_timeout=cfg.get("connection_timeout", 10.0),
            request_timeout=cfg.get("request_timeout", 5.0),
            heartbeat_interval=cfg.get("heartbeat_interval", 15.0),
            login_timeout=cfg.get("login_timeout", 10.0),
            auto_reconnect=cfg.get("auto_reconnect", True),
            max_retries=cfg.get("max_retries", 5),
            base_delay=cfg.get("base_delay", 1.0),
            max_delay=cfg.get("max_delay", 60.0),
            exponential_base=cfg.get("exponential_base", 2.0),
        )
        return GlobalConfig.from_connection_config(conn)

    async def configure_master(self, config: dict[str, Any]) -> None:
        """Set master account configuration. Must be called before start()."""
        self._master_config = config
        logger.info(
            "Master account configured: %s@%s:%s",
            config["username"],
            config["host"],
            config["port"],
        )

    async def configure_follower(
        self, follower_id: str, config: dict[str, Any]
    ) -> None:
        """Add or update a follower account configuration."""
        self._follower_configs[follower_id] = config
        logger.info(
            "Follower %s configured: %s@%s:%s",
            follower_id,
            config["username"],
            config["host"],
            config["port"],
        )

    async def remove_follower(self, follower_id: str) -> None:
        """Remove a follower. Stops its client if running."""
        if follower_id in self._follower_clients:
            client = self._follower_clients.pop(follower_id)
            try:
                await client.stop()
            except Exception as e:
                logger.warning("Error stopping follower %s: %s", follower_id, e)
        self._follower_configs.pop(follower_id, None)

    async def start(self) -> None:
        """Start master and all follower clients."""
        if self._running:
            logger.warning("DASService already running")
            return

        if not self._master_config:
            raise RuntimeError("Master account not configured")

        # Start master
        master_cfg = self._build_config(self._master_config)
        self._master_client = DASClient(master_cfg)
        await self._master_client.start()
        logger.info("Master client started")

        # Start followers concurrently
        start_tasks: list[asyncio.Task[None]] = []
        for fid, fcfg in self._follower_configs.items():
            client = DASClient(self._build_config(fcfg))
            self._follower_clients[fid] = client
            start_tasks.append(asyncio.ensure_future(self._start_follower(fid, client)))

        if start_tasks:
            results = await asyncio.gather(*start_tasks, return_exceptions=True)
            for fid, result in zip(self._follower_configs.keys(), results):
                if isinstance(result, Exception):
                    logger.error("Failed to start follower %s: %s", fid, result)

        self._running = True
        logger.info("DASService started with %d followers", len(self._follower_clients))

    async def _start_follower(self, follower_id: str, client: DASClient) -> None:
        """Start a single follower client."""
        await client.start()
        logger.info("Follower %s client started", follower_id)

    async def stop(self) -> None:
        """Stop all clients gracefully."""
        if not self._running:
            return

        # Stop followers concurrently
        stop_tasks: list[asyncio.Task[None]] = []
        for fid, client in self._follower_clients.items():
            stop_tasks.append(asyncio.ensure_future(self._stop_client(fid, client)))

        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)

        # Stop master
        if self._master_client:
            try:
                await self._master_client.stop()
            except Exception as e:
                logger.warning("Error stopping master: %s", e)
            self._master_client = None

        self._follower_clients.clear()
        self._running = False
        logger.info("DASService stopped")

    async def _stop_client(self, name: str, client: DASClient) -> None:
        try:
            await client.stop()
            logger.info("Client %s stopped", name)
        except Exception as e:
            logger.warning("Error stopping %s: %s", name, e)

    def get_status(self) -> dict[str, Any]:
        """Return connection status for all clients."""
        status: dict[str, Any] = {
            "running": self._running,
            "master": {
                "configured": self._master_config is not None,
                "connected": self._master_client.is_running
                if self._master_client
                else False,
            },
            "followers": {},
        }
        for fid, client in self._follower_clients.items():
            status["followers"][fid] = {
                "connected": client.is_running,
            }
        return status
