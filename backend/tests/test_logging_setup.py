from __future__ import annotations

import logging
from types import SimpleNamespace

from paxveil import logging_setup


def test_native_logs_bound_disk_usage_and_hide_configured_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("PAXVEIL_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(
        logging_setup,
        "get_settings",
        lambda: SimpleNamespace(
            database_url="postgresql+psycopg://paxveil:fixture%2Fpassword@db/paxveil",
            telegram_token="fixture-private-token",
            bot_key="fixture-service-key",
        ),
    )
    root = logging.getLogger()
    original_handlers, original_level = root.handlers[:], root.level
    names = ["uvicorn", "uvicorn.error", "uvicorn.access"]
    original_loggers = {
        name: (logging.getLogger(name).handlers[:], logging.getLogger(name).propagate, logging.getLogger(name).disabled)
        for name in names
    }
    root.handlers.clear()
    try:
        logging_setup.configure_native_logging("api")
        logger = logging.getLogger("paxveil.synthetic.rotation")
        for counter in range(12):
            logger.info(
                "entry=%d %s private=%s pass=%s", counter, "x" * 1_048_576, "fixture-private-token", "fixture/password"
            )
        try:
            raise ValueError("postgresql+psycopg://paxveil:fixture%2Fpassword@db/paxveil key=fixture-service-key")
        except ValueError:
            logger.exception("Controlled driver failure")
        for handler in root.handlers:
            handler.flush()
        files = list(tmp_path.glob("api.log*"))
        assert 2 <= len(files) <= 4
        assert sum(path.stat().st_size for path in files) <= 16 * 1_048_576
        combined = "".join(path.read_text(encoding="utf-8") for path in files)
        assert "entry=11" in combined
        assert "Controlled driver failure" in combined
        for secret in [
            "fixture-private-token",
            "fixture-service-key",
            "fixture/password",
            "fixture%2Fpassword",
            "postgresql+psycopg://paxveil",
        ]:
            assert secret not in combined
        assert logging.getLogger("uvicorn.access").disabled
    finally:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
            handler.close()
        root.handlers[:] = original_handlers
        root.setLevel(original_level)
        for name, (handlers, propagate, disabled) in original_loggers.items():
            logger = logging.getLogger(name)
            logger.handlers[:] = handlers
            logger.propagate, logger.disabled = propagate, disabled


def test_without_native_directory_preserves_stdout_handlers(monkeypatch):
    monkeypatch.delenv("PAXVEIL_LOG_DIR", raising=False)
    root = logging.getLogger()
    original_handlers, original_level = root.handlers[:], root.level
    logging_setup.configure_native_logging("worker")
    assert root.handlers == original_handlers
    assert root.level == original_level
