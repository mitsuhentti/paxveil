from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, LinkPreviewOptions

from ..logging_setup import configure_native_logging
from .client import ApiClient
from .config import BotConfig
from .handlers import BotService, build_dispatcher
from .log_safety import protect_logs


async def main() -> None:
    config = BotConfig.from_env()
    configure_native_logging("bot")
    protect_logs(config.token, config.bot_key)
    api = ApiClient(config.api_url, config.bot_key)
    bot = Bot(
        token=config.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview=LinkPreviewOptions(is_disabled=True)),
    )
    service = BotService(api, config)
    dispatcher = build_dispatcher(service)
    try:
        # Only happens when the operator explicitly runs the configured bot.
        await bot.delete_webhook(drop_pending_updates=False)
        commands = [
            BotCommand(command="start", description="Главное меню PAXVEIL"),
            BotCommand(command="example", description="Попробовать проверку на примере"),
            BotCommand(command="projects", description="Мои проекты"),
            BotCommand(command="vulnerabilities", description="Уязвимости проектов"),
            BotCommand(command="fixlab", description="Сравнить варианты обновления"),
            BotCommand(command="fire", description="Проверить CVE во всех проектах"),
            BotCommand(command="watch", description="Управление мониторингом"),
            BotCommand(
                command="settings",
                description="Уведомления и среда проверки",
            ),
            BotCommand(command="environment", description="Среда новых проектов"),
            BotCommand(command="privacy", description="Как хранятся ваши данные"),
            BotCommand(command="export", description="Скачать свои данные"),
            BotCommand(command="delete_account", description="Удалить все свои данные"),
        ]
        if config.public_web_url:
            commands.append(BotCommand(command="link", description="Связать Telegram одноразовым кодом"))
        await bot.set_my_commands(commands)
        await bot.set_my_commands(commands, language_code="ru")
        await dispatcher.start_polling(
            bot,
            tasks_concurrency_limit=64,
            allowed_updates=["message", "callback_query"],
        )
    except TelegramAPIError as exc:
        logging.getLogger(__name__).error("telegram_startup_failed error_type=%s", type(exc).__name__)
        raise SystemExit("Telegram startup failed. Check bot credentials and network access.") from None
    finally:
        await api.close()
        await bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    try:
        asyncio.run(main())
    except (ValueError, KeyboardInterrupt) as exc:
        if isinstance(exc, ValueError):
            raise SystemExit(str(exc)) from None
