"""Telegram dispatcher -> real ASGI API -> isolated DB/worker; no external traffic."""

from __future__ import annotations

import importlib

import httpx
import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from sqlalchemy import select
from test_api import api_env, fixture_report  # noqa: F401 -- imported pytest fixture
from test_bot import SYNTHETIC_TOKEN, USER, RecordingTelegram

from paxveil.bot.client import ApiClient
from paxveil.bot.config import BotConfig
from paxveil.bot.handlers import BotService, build_dispatcher


@pytest.mark.asyncio
async def test_real_bot_api_worker_watch_and_web_link_contract(api_env, monkeypatch):  # noqa: F811
    telegram = RecordingTelegram()
    bot = Bot(
        SYNTHETIC_TOKEN,
        session=telegram,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    api = ApiClient(
        "http://testserver",
        api_env.settings.bot_key,
        transport=httpx.ASGITransport(app=api_env.api.app),
    )
    service = BotService(
        api, BotConfig(SYNTHETIC_TOKEN, api_env.settings.bot_key, wait_seconds=0)
    )
    dispatcher = build_dispatcher(service)
    counter = 0

    async def feed(text=None, document=None, callback=None):
        nonlocal counter
        counter += 1
        actor = {"id": USER, "is_bot": False, "first_name": "Synthetic Owner"}
        message = {
            "message_id": counter,
            "date": 1_700_000_000,
            "chat": {"id": USER, "type": "private"},
            "from": actor,
        }
        if text:
            message["text"] = text
            if text.startswith("/"):
                message["entities"] = [
                    {"type": "bot_command", "offset": 0, "length": len(text.split()[0])}
                ]
        if document:
            message["document"] = {
                "file_id": "synthetic-file",
                "file_unique_id": "fixture",
                **document,
            }
        if callback:
            message["from"] = {
                "id": bot.id,
                "is_bot": True,
                "first_name": "PAXVEIL Bot",
            }
            update = {
                "update_id": counter,
                "callback_query": {
                    "id": str(counter),
                    "chat_instance": "fixture",
                    "from": actor,
                    "message": message,
                    "data": callback,
                },
            }
        else:
            update = {"update_id": counter, "message": message}
        await dispatcher.feed_raw_update(bot, update)

    await feed(text="/start")
    await feed(
        document={"file_name": "requirements.txt", "file_size": len(telegram.content)}
    )
    with api_env.factory() as db:
        project = db.scalar(select(api_env.db.Project))
        assert project is not None and project.filename == "requirements.txt"
        project_id = project.id
        scan = db.scalar(select(api_env.db.Scan))
        assert scan.status == "queued"

    worker = importlib.import_module("paxveil.worker")
    core = importlib.import_module("paxveil.core.service")
    monkeypatch.setattr(worker, "SessionLocal", api_env.factory)
    monkeypatch.setattr(worker, "settings", api_env.settings)

    async def controlled_scan(*args, **kwargs):
        return fixture_report()

    monkeypatch.setattr(core, "scan", controlled_scan)
    claimed = worker.claim_job()
    assert claimed is not None
    await worker.execute(*claimed)
    await feed(callback=f"watch:{project_id}:1")
    with api_env.factory() as db:
        assert db.get(api_env.db.Subscription, project_id).enabled
        assert db.get(api_env.db.Scan, scan.id).status == "completed"
    assert any("Известных уязвимостей: <b>1</b>" in output for output in telegram.texts)

    web_owner = api_env.owner("linked_web_fixture")
    browser = api_env.client(web_owner)
    code = browser.post("/api/auth/telegram/link").json()["code"]
    await feed(text="/link " + code)
    await feed(text="/projects")
    visible = browser.get("/api/projects").json()
    assert [project["id"] for project in visible] == [project_id]
    assert visible[0]["watch"] is True
    assert any("Telegram связан" in output for output in telegram.texts)
    assert all(code not in output for output in telegram.texts)
    with api_env.factory() as db:
        assert db.get(api_env.db.Project, project_id).user_id == web_owner.id
        assert db.get(api_env.db.User, web_owner.id).telegram_id == str(USER)
    await api.close()
    await bot.session.close()
