from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


@dataclass(frozen=True)
class BotConfig:
    token: str = field(repr=False)
    bot_key: str = field(repr=False)
    api_url: str = "http://localhost:8000"
    web_url: str = "http://localhost:3000"
    max_file_bytes: int = 1_048_576
    poll_seconds: float = 4.0
    wait_seconds: float = 120.0

    @classmethod
    def from_env(cls) -> BotConfig:
        load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        key = os.getenv("PAXVEIL_BOT_KEY", "").strip()
        if not token or not key:
            raise ValueError(
                "Set TELEGRAM_BOT_TOKEN and PAXVEIL_BOT_KEY in the local .env. "
                "Never paste secrets into chat. See docs/TELEGRAM.md."
            )
        config = cls(
            token=token,
            bot_key=key,
            api_url=os.getenv("PAXVEIL_API_URL", "http://localhost:8000").rstrip("/"),
            web_url=os.getenv("PAXVEIL_WEB_URL", "http://localhost:3000").rstrip("/"),
        )
        api = urlsplit(config.api_url)
        if (
            api.scheme not in {"http", "https"}
            or not api.hostname
            or api.username
            or api.password
        ):
            raise ValueError(
                "PAXVEIL_API_URL must be an HTTP(S) service URL without credentials."
            )
        if api.scheme == "http" and api.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
            "api",
            "backend",
        }:
            raise ValueError(
                "Use HTTPS when PAXVEIL_API_URL is outside the local host/container network."
            )
        web = urlsplit(config.web_url)
        if (
            web.scheme not in {"http", "https"}
            or not web.hostname
            or web.username
            or web.password
        ):
            raise ValueError(
                "PAXVEIL_WEB_URL must be an HTTP(S) URL without credentials."
            )
        return config
