from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, LinkPreviewOptions

from .client import ApiClient
from .config import BotConfig
from .handlers import BotService, build_dispatcher


async def main() -> None:
    config = BotConfig.from_env()
    api = ApiClient(config.api_url, config.bot_key)
    bot = Bot(
        token=config.token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML, link_preview=LinkPreviewOptions(is_disabled=True)
        ),
    )
    service = BotService(api, config)
    dispatcher = build_dispatcher(service)
    try:
        # Only happens when the operator explicitly runs the configured bot.
        await bot.delete_webhook(drop_pending_updates=False)
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Главное меню PAXVEIL"),
                BotCommand(command="projects", description="Мои проекты"),
                BotCommand(
                    command="vulnerabilities", description="Уязвимости проектов"
                ),
                BotCommand(
                    command="fixlab", description="Сравнить варианты обновления"
                ),
                BotCommand(
                    command="fire", description="Проверить CVE во всех проектах"
                ),
                BotCommand(command="watch", description="Управление мониторингом"),
                BotCommand(
                    command="settings",
                    description="Уведомления и связь с веб-аккаунтом",
                ),
                BotCommand(
                    command="link", description="Связать Telegram одноразовым кодом"
                ),
            ],
            language_code="ru",
        )
        await dispatcher.start_polling(
            bot,
            tasks_concurrency_limit=64,
            allowed_updates=["message", "callback_query"],
        )
    finally:
        await api.close()
        await bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    try:
        asyncio.run(main())
    except (ValueError, KeyboardInterrupt) as exc:
        if isinstance(exc, ValueError):
            raise SystemExit(str(exc)) from None
