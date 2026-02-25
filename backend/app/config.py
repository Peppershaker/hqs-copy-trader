"""Application configuration via environment variables and .env file."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class AppConfig(BaseSettings):
    """Global application settings loaded from env / .env."""

    # Server
    app_host: str = "127.0.0.1"
    app_port: int = 8787
    open_browser: bool = True

    # Database
    db_path: str = "./das_copy_trader.db"

    # Logging
    log_level: str = "INFO"

    # Frontend static dir (filled at build time)
    static_dir: str = ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

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
