from __future__ import annotations

import logging

from ..logging_setup import SecretFilter


def protect_logs(*secrets: str) -> None:
    # Attach to output handlers: logger-level filters do not run for descendants
    # such as aiogram.dispatcher, whose retry errors include SDK exception text.
    for handler in logging.getLogger().handlers:
        handler.addFilter(SecretFilter(*secrets))
