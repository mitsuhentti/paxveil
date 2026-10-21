from __future__ import annotations

import logging
import os
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .config import get_settings


class SecretFilter(logging.Filter):
    """Redact configured credentials from SDK/driver messages and tracebacks."""

    def __init__(self, *secrets: str):
        super().__init__()
        self._secrets = tuple(sorted({value for value in secrets if value}, key=len, reverse=True))

    def _redact(self, value: str) -> str:
        for secret in self._secrets:
            value = value.replace(secret, "[redacted]")
        return value

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._redact(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.exc_text = self._redact("".join(traceback.format_exception(*record.exc_info)))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = self._redact(record.exc_text)
        return True


def configured_secret_filter() -> SecretFilter:
    settings = get_settings()
    url = settings.database_url
    password = urlsplit(url).password or ""
    return SecretFilter(
        settings.telegram_token,
        settings.bot_key,
        url,
        url.replace("postgresql+psycopg:", "postgresql:"),
        password,
        unquote(password),
    )


def configure_native_logging(component: str) -> None:
    """Bound native log storage; containers keep their existing stdout logging."""
    directory = os.getenv("PAXVEIL_LOG_DIR")
    if not directory:
        return
    if component not in {"api", "worker", "bot"}:
        raise ValueError("Unknown PAXVEIL logging component")
    log_directory = Path(directory).resolve()
    log_directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_directory / f"{component}.log", maxBytes=4 * 1_048_576, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(configured_secret_filter())
    root = logging.getLogger()
    for previous in root.handlers[:]:
        root.removeHandler(previous)
        previous.close()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        for previous in logger.handlers[:]:
            logger.removeHandler(previous)
            previous.close()
        logger.propagate = True
        logger.disabled = False
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.disabled = True
