"""Application configuration via environment variables and .env file."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_settings import BaseSettings


class DasServerConfig(BaseModel):
    """A single DAS-bridge server entry from the DAS_SERVERS env var."""

    broker_id: str
    host: str
    port: int
    username: str
    password: str
    accounts: list[str] = []
    smart_routes: list[str] = []
    locate_routes: dict[str, int] = {}

    @property
    def broker_id_lower(self) -> str:
        return self.broker_id.lower()


class AppConfig(BaseSettings):
    """Global application settings loaded from env / .env."""

    # Server
    app_host: str = "127.0.0.1"
    app_port: int = 8787

    # Database
    db_path: str = "./das_copy_trader.db"

    # Logging
    log_level: str = "INFO"

    # Frontend static dir (filled at build time)
    static_dir: str = ""

    # DAS-bridge server configurations (JSON array string)
    das_servers: str = "[]"

    model_config = {
        "extra": "ignore",
    }

    @property
    def parsed_das_servers(self) -> list[DasServerConfig]:
        """Parse the DAS_SERVERS JSON string into a list of DasServerConfig objects."""
        try:
            data: list[dict[str, Any]] = json.loads(self.das_servers)
            return [DasServerConfig(**item) for item in data]
        except Exception:
            return []

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"

    @property
    def resolved_static_dir(self) -> Path | None:
        """Resolve the static directory for serving the frontend."""
        if self.static_dir:
            p = Path(self.static_dir)
            if p.is_dir():
                return p

        # Check common locations relative to this file
        candidates = [
            Path(__file__).parent / "static",
            Path(__file__).parent.parent / "static",
            Path(os.getcwd()) / "static",
        ]
        for c in candidates:
            if c.is_dir():
                return c
        return None


_config: AppConfig | None = None


def get_config() -> AppConfig:
    global _config
    if _config is None:
        _config = AppConfig()
    return _config


def reset_config() -> None:
    """Reset the cached config so the next get_config() picks up new env vars."""
    global _config
    _config = None


def parse_env_text(content: str) -> dict[str, str]:
    """Parse raw .env text into a key→value dict (comments and blanks excluded)."""
    import io

    from dotenv import dotenv_values

    return {
        k: v
        for k, v in dotenv_values(stream=io.StringIO(content)).items()
        if k and v is not None
    }


def apply_env_text(content: str) -> dict[str, str]:
    """Parse raw .env text, push every key into os.environ, reset the config cache.

    Returns the dict of key→value pairs that were parsed (comments and blanks excluded).
    """
    parsed = parse_env_text(content)
    for key, value in parsed.items():
        os.environ[key] = value
    reset_config()
    return parsed
