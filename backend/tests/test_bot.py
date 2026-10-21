"""Synthetic Telegram updates and controlled API fixtures; no Telegram network calls."""

from __future__ import annotations

import asyncio
import io
import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import GetFile, SendDocument, SendMessage
from aiogram.types import File, Message

from paxveil.bot.client import ApiClient, ApiError
from paxveil.bot.config import BotConfig
from paxveil.bot.handlers import BotService, BoundedBuffer, build_dispatcher
from paxveil.bot.log_safety import SecretFilter
from paxveil.bot.presentation import MENU, finding_summary

USER = 44
PROJECT = "11111111-1111-4111-8111-111111111111"
SCAN = "22222222-2222-4222-8222-222222222222"
JOB = "33333333-3333-4333-8333-333333333333"
OTHER_PROJECT = "44444444-4444-4444-8444-444444444444"
# This is a syntactically valid synthetic token. It never reaches a network.
SYNTHETIC_TOKEN = "123456789:AA_SYNTHETIC_TEST_TOKEN_1234567890123"


class RecordingTelegram(BaseSession):
    def __init__(self):
        super().__init__()
        self.methods: list[Any] = []
        self.content = b"fixture-package==1.0\n"
        self.downloads = 0

    async def close(self) -> None:
        pass

    async def make_request(self, bot: Bot, method: Any, timeout: int | None = None) -> Any:
        self.methods.append(method)
        if isinstance(method, GetFile):
            return File(
                file_id="synthetic-file",
                file_unique_id="fixture",
                file_size=len(self.content),
                file_path="documents/fixture.txt",
            )
        if isinstance(method, (SendMessage, SendDocument)):
            return Message(
                message_id=100 + len(self.methods),
                date=datetime.now(UTC),
                chat={"id": USER, "type": "private"},
                from_user={"id": bot.id, "is_bot": True, "first_name": "PAXVEIL Bot"},
                text=method.text if isinstance(method, SendMessage) else method.caption,
            )
        return True

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ):
        self.downloads += 1
        for offset in range(0, len(self.content), chunk_size):
            yield self.content[offset : offset + chunk_size]

    @property
    def texts(self) -> list[str]:
        return [m.text for m in self.methods if isinstance(m, SendMessage)]


def fixture_report() -> dict[str, Any]:
    # Intentionally artificial identifiers and versions, only in test fixtures.
    return {
        "dependencies": [{"name": "fixture-package", "version": "1.0", "direct": True}],
        "stats": {"dependencies": 1, "findings": 1},
        "completeness": "complete",
        "warnings": [],
        "findings": [
            {
                "id": "TEST-ADVISORY-1",
                "package": "fixture-package",
                "version": "1.0",
                "severity": "high",
                "priority": 77,
                "cvss": 8.1,
                "epss": 0.01,
                "summary": "<unsafe>tag & text",
                "fixed_versions": ["1.1"],
                "priority_reasons": ["fixture"],
            }
        ],
    }


def fixture_project() -> dict[str, Any]:
    return {
        "id": PROJECT,
        "name": "<fixture> & project",
        "watch": False,
        "latest_scan": {"id": SCAN, "status": "completed", "report": fixture_report()},
    }


def fixture_settings() -> dict[str, Any]:
    return {
        "telegram_id": USER,
        "timezone": "UTC",
        "quiet_start": None,
        "quiet_end": None,
        "minimum_priority": 60,
        "digest": False,
        "categories": ["new", "priority", "fix", "exploitation", "status"],
        "upload_python_version": "3.11",
        "upload_platform": "linux",
    }


class FixtureAPI:
    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.settings = fixture_settings()
        self.scan_states = ["completed"]
        self.scan_error = None
        self.job_states = ["succeeded"]
        self.project = fixture_project()
        self.watch = False
        self.deleted = 0
        self.linked = False
        self.refreshed = 0
        self.force_401 = False
        self.account_deleted = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        path = request.url.path
        if path in {"/api/bot/identity", "/api/bot/link"}:
            assert request.headers["X-Bot-Key"] == "synthetic-bot-key"
            assert "Authorization" not in request.headers
            body = json.loads(request.content)
            assert body["telegram_id"] == USER
            if path.endswith("link"):
                if self.linked:
                    return httpx.Response(400, json={"detail": "one-use code consumed"})
                assert body["code"] == "SYNTHETIC_CODE"
                self.linked = True
            else:
                self.refreshed += 1
            token = "linked-session" if self.linked else "synthetic-session"
            return httpx.Response(
                200,
                json={
                    "token": token,
                    "user": {"id": "fixture-owner", "username": "fixture-user"},
                },
            )
        assert request.headers["Authorization"] == (
            "Bearer linked-session" if self.linked else "Bearer synthetic-session"
        )
        assert "X-Bot-Key" not in request.headers
        if self.force_401:
            self.force_401 = False
            return httpx.Response(401, json={"detail": "expired"})
        if OTHER_PROJECT in path:
            return httpx.Response(404, json={"detail": "private"})
        if path == "/api/projects":
            if request.method == "POST":
                assert b"fixture-package==1.0" in request.content or b"requests==2.31.0\n" in request.content
                return httpx.Response(
                    201,
                    json={
                        **self.project,
                        "latest_scan": {"id": SCAN, "status": "queued"},
                    },
                )
            return httpx.Response(200, json=[] if self.deleted else [self.project])
        if path == f"/api/projects/{PROJECT}":
            if request.method == "DELETE":
                self.deleted += 1
                return httpx.Response(204)
            return httpx.Response(200, json={**self.project, "watch": self.watch})
        if path.endswith("/watch"):
            self.watch = json.loads(request.content)["enabled"]
            return httpx.Response(200, json={"enabled": self.watch})
        if path == f"/api/projects/{PROJECT}/scan":
            return httpx.Response(200, json={"id": JOB, "scan_id": SCAN, "status": "pending"})
        if path == f"/api/scans/{SCAN}":
            status = self.scan_states.pop(0) if len(self.scan_states) > 1 else self.scan_states[0]
            return httpx.Response(
                200,
                json={
                    "id": SCAN,
                    "status": status,
                    "report": fixture_report() if status == "completed" else None,
                    "error": self.scan_error,
                },
            )
        if path == f"/api/scans/{SCAN}/fixlab":
            return httpx.Response(200, json={"id": JOB, "status": "pending"})
        if path == f"/api/jobs/{JOB}":
            status = self.job_states.pop(0) if len(self.job_states) > 1 else self.job_states[0]
            strategies = [
                {
                    "name": name,
                    "status": "resolved",
                    "updates": [{"package": "fixture-package", "from": "1.0", "to": "1.1"}],
                    "before": {"dependencies": 1, "findings": 1},
                    "after": {"dependencies": 1, "findings": 0},
                    "reason": "Fixture only",
                    "conflicts": [],
                    "uncertainties": [],
                }
                for name in ["Minimal Change", "Balanced", "Maximum Coverage"]
            ]
            return httpx.Response(
                200,
                json={
                    "id": JOB,
                    "status": status,
                    "result": {
                        "strategies": strategies,
                        "limitations": ["Synthetic test fixture"],
                    },
                },
            )
        if path == "/api/fire":
            assert json.loads(request.content) == {"cve": "CVE-2024-35195"}
            return httpx.Response(
                200,
                json={
                    "cve": "CVE-2024-35195",
                    "status": "found",
                    "limitations": ["Synthetic API fixture"],
                    "matches": [
                        {
                            "project_id": PROJECT,
                            "project_name": "<fixture> & project",
                            "package": "fixture-package",
                            "version": "1.0",
                            "status": "affected",
                        }
                    ],
                },
            )
        if path == "/api/settings":
            if request.method == "PUT":
                patch = json.loads(request.content)
                assert "telegram_id" not in patch
                self.settings.update(patch)
            return httpx.Response(200, json=self.settings)
        if path == "/api/account/export":
            return httpx.Response(
                200, json={"schema_version": 1, "account": {"telegram_id": USER}, "projects": [self.project]}
            )
        if path == "/api/account" and request.method == "DELETE":
            assert json.loads(request.content) == {"confirmation": "DELETE"}
            self.account_deleted += 1
            return httpx.Response(200, json={"ok": True})
        raise AssertionError(f"Unexpected fixture path: {path}")


@pytest.fixture
def harness():
    class Harness:
        def __init__(self):
            self.fixture = FixtureAPI()
            self.telegram = RecordingTelegram()
            self.bot = Bot(
                SYNTHETIC_TOKEN,
                session=self.telegram,
                default=DefaultBotProperties(parse_mode="HTML"),
            )
            self.api = ApiClient(
                "http://localhost:8000",
                "synthetic-bot-key",
                transport=httpx.MockTransport(self.fixture),
            )
            self.service = BotService(
                self.api,
                BotConfig(
                    SYNTHETIC_TOKEN,
                    "synthetic-bot-key",
                    poll_seconds=0,
                    wait_seconds=0.5,
                ),
            )
            self.dispatcher = build_dispatcher(self.service)
            self.update_id = 0

        async def feed(
            self,
            *,
            text: str | None = None,
            callback: str | None = None,
            document: dict[str, Any] | None = None,
            chat_type: str = "private",
            actor: int = USER,
        ):
            self.update_id += 1
            message = {
                "message_id": self.update_id,
                "date": 1_700_000_000,
                "chat": {
                    "id": USER if chat_type == "private" else -1234,
                    "type": chat_type,
                },
                "from": {"id": actor, "is_bot": False, "first_name": "Fixture"},
            }
            if text is not None:
                message["text"] = text
                if text.startswith("/"):
                    message["entities"] = [
                        {
                            "type": "bot_command",
                            "offset": 0,
                            "length": len(text.split()[0]),
                        }
                    ]
            if document is not None:
                message["document"] = {
                    "file_id": "synthetic-file",
                    "file_unique_id": "fixture",
                    **document,
                }
            if callback is not None:
                # callback message author is the bot, actor is a separate real user.
                message["from"] = {
                    "id": self.bot.id,
                    "is_bot": True,
                    "first_name": "PAXVEIL Bot",
                }
                update = {
                    "update_id": self.update_id,
                    "callback_query": {
                        "id": str(self.update_id),
                        "chat_instance": "fixture",
                        "from": {"id": actor, "is_bot": False, "first_name": "Fixture"},
                        "message": message,
                        "data": callback,
                    },
                }
            else:
                update = {"update_id": self.update_id, "message": message}
            return await self.dispatcher.feed_raw_update(self.bot, update)

    return Harness()


@pytest.mark.asyncio
async def test_start_menu_and_bearer_auth(harness):
    await harness.feed(text="/start")
    start = next(m for m in harness.telegram.methods if isinstance(m, SendMessage))
    assert {b.text for row in start.reply_markup.keyboard for b in row} == set(MENU)
    await harness.feed(text="/projects")
    assert any("Мои проекты" in s for s in harness.telegram.texts)
    assert len(harness.fixture.calls) == 2
    assert harness.fixture.calls[1].headers["Authorization"] == "Bearer synthetic-session"
    assert all(SYNTHETIC_TOKEN not in s for s in harness.telegram.texts)


@pytest.mark.asyncio
async def test_group_and_mismatched_private_actor_never_reach_api(harness):
    await harness.feed(text="/projects", chat_type="group")
    await harness.feed(callback=f"project:{PROJECT}", actor=USER + 1)
    assert not harness.fixture.calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filename,size",
    [
        ("../requirements.txt", 100),
        ("script.py", 100),
        ("requirements.txt", 1_048_577),
        ("requirements.txt", 0),
    ],
)
async def test_bad_document_rejected_before_download(harness, filename, size):
    await harness.feed(document={"file_name": filename, "file_size": size})
    assert not harness.fixture.calls
    assert harness.telegram.downloads == 0


def test_bounded_download_sink_enforces_bytes_even_when_metadata_underreports():
    sink = BoundedBuffer(5)
    sink.write(b"1234")
    with pytest.raises(ValueError):
        sink.write(b"56")
    assert len(sink.getvalue()) == 4


@pytest.mark.asyncio
async def test_file_upload_polls_real_statuses_and_reports_fixture_stats(harness):
    harness.fixture.scan_states = ["queued", "running", "completed"]
    await harness.feed(
        document={
            "file_name": "requirements.txt",
            "file_size": len(harness.telegram.content),
        }
    )
    assert harness.telegram.downloads == 1
    assert any(r.method == "POST" and r.url.path == "/api/projects" for r in harness.fixture.calls)
    messages = "\n".join(harness.telegram.texts)
    assert "В очереди" in messages and "Проверяется" in messages
    assert "Зависимостей: <b>1</b>" in messages
    assert "77/100" in messages
    assert "&lt;fixture&gt; &amp; project" in messages


@pytest.mark.asyncio
async def test_stream_size_limit_even_if_document_and_getfile_metadata_lie(harness):
    harness.service.config = BotConfig(SYNTHETIC_TOKEN, "synthetic-bot-key", max_file_bytes=5)
    harness.telegram.content = b"123456"
    original = harness.telegram.make_request

    async def wrong_metadata(bot, method, timeout=None):
        if isinstance(method, GetFile):
            return File(
                file_id="synthetic-file",
                file_unique_id="fixture",
                file_size=2,
                file_path="documents/fixture.txt",
            )
        return await original(bot, method, timeout)

    harness.telegram.make_request = wrong_metadata
    await harness.feed(document={"file_name": "requirements.txt", "file_size": 2})
    assert not harness.fixture.calls
    assert any("превышает" in s for s in harness.telegram.texts)


@pytest.mark.asyncio
async def test_unknown_callback_cannot_inject_api_path(harness):
    await harness.feed(callback="project:../../settings")
    await harness.feed(callback=f"watch:{PROJECT}:2")
    assert not harness.fixture.calls


@pytest.mark.asyncio
async def test_forged_object_id_is_owner_checked_by_api(harness):
    await harness.feed(callback=f"project:{OTHER_PROJECT}")
    assert any("недоступен" in s for s in harness.telegram.texts)
    assert not any("<fixture>" in s for s in harness.telegram.texts)
    assert harness.fixture.calls[-1].headers["Authorization"] == "Bearer synthetic-session"


@pytest.mark.asyncio
async def test_watch_callback_uses_callback_actor_and_persisted_api_setting(harness):
    await harness.feed(callback=f"watch:{PROJECT}:1")
    assert harness.fixture.watch is True
    assert any("Мониторинг: включён" in s for s in harness.telegram.texts)
    await harness.feed(callback=f"watch:{PROJECT}:0")
    assert harness.fixture.watch is False


@pytest.mark.asyncio
async def test_report_escapes_html_and_sends_owner_report_json(harness):
    await harness.feed(callback=f"report:{PROJECT}")
    assert any("&lt;unsafe&gt;tag &amp; text" in s for s in harness.telegram.texts)
    documents = [m for m in harness.telegram.methods if isinstance(m, SendDocument)]
    assert len(documents) == 1
    assert json.loads(documents[0].document.data)["stats"] == {
        "dependencies": 1,
        "findings": 1,
    }
    assert not any("localhost" in s for s in harness.telegram.texts)
    assert not any("http://" in s for s in harness.telegram.texts)


@pytest.mark.asyncio
async def test_fixlab_selects_project_then_strategy_and_waits_for_job(harness):
    await harness.feed(text="/fixlab")
    await harness.feed(callback=f"strategies:{PROJECT}")
    harness.fixture.job_states = ["pending", "running", "succeeded"]
    await harness.feed(callback=f"fix:{PROJECT}:1")
    assert any("В пределах major-версии" in s for s in harness.telegram.texts)
    assert any("fixture-package" in s and "1.0 → 1.1" in s for s in harness.telegram.texts)
    assert any(r.method == "POST" and r.url.path == f"/api/scans/{SCAN}/fixlab" for r in harness.fixture.calls)


@pytest.mark.asyncio
async def test_fire_cve_validation_and_controlled_api_fixture(harness):
    await harness.feed(text="/fire bad-CVE ../../anything")
    assert not harness.fixture.calls
    await harness.feed(text="/fire cve-2024-35195")
    assert any("Потенциально затронутых записей: 1" in s for s in harness.telegram.texts)
    assert any("Synthetic API fixture" in s for s in harness.telegram.texts)


@pytest.mark.asyncio
async def test_deletion_requires_live_single_use_confirmation(harness):
    await harness.feed(callback=f"confirm:{PROJECT}:0000000000000000")
    assert not harness.fixture.calls
    await harness.feed(callback=f"delete:{PROJECT}")
    nonce = harness.service._confirmations[(USER, PROJECT)][0]
    await harness.feed(callback=f"confirm:{PROJECT}:{nonce}")
    assert harness.fixture.deleted == 1
    await harness.feed(callback=f"confirm:{PROJECT}:{nonce}")
    assert harness.fixture.deleted == 1


@pytest.mark.asyncio
async def test_settings_validation_and_persistent_update(harness):
    await harness.feed(text="/priority 101")
    await harness.feed(text="/quiet 30:00 22:00")
    assert not harness.fixture.calls
    await harness.feed(text="/quiet 22:00 08:00")
    await harness.feed(text="/priority 75")
    await harness.feed(text="/category new off")
    assert harness.fixture.settings["quiet_start"] == "22:00"
    assert harness.fixture.settings["quiet_end"] == "08:00"
    assert harness.fixture.settings["minimum_priority"] == 75
    assert "new" not in harness.fixture.settings["categories"]
    assert all("telegram_id" not in json.loads(r.content) for r in harness.fixture.calls if r.method == "PUT")


@pytest.mark.asyncio
async def test_link_consumes_code_updates_bearer_and_never_echoes_code(harness):
    await harness.feed(text="/link SYNTHETIC_CODE")
    await harness.feed(text="/projects")
    assert harness.fixture.linked
    assert harness.fixture.calls[-1].headers["Authorization"] == "Bearer linked-session"
    assert all("SYNTHETIC_CODE" not in s for s in harness.telegram.texts)
    await harness.feed(text="/link SYNTHETIC_CODE")
    assert any("не принят" in s for s in harness.telegram.texts)


@pytest.mark.asyncio
async def test_expired_session_reauthenticates_once(harness):
    await harness.api.identity(USER)
    harness.fixture.force_401 = True
    projects = await harness.api.projects(USER)
    assert projects[0]["id"] == PROJECT
    assert harness.fixture.refreshed == 2


@pytest.mark.asyncio
async def test_poll_timeout_keeps_persisted_job_and_exposes_refresh(harness):
    harness.service.config = BotConfig(SYNTHETIC_TOKEN, "synthetic-bot-key", wait_seconds=0, poll_seconds=0)
    harness.fixture.job_states = ["retry"]
    await harness.feed(callback=f"fix:{PROJECT}:2")
    assert any("продолжает выполняться" in s for s in harness.telegram.texts)
    refresh = [m.reply_markup for m in harness.telegram.methods if isinstance(m, SendMessage) and m.reply_markup]
    assert any(
        b.callback_data == f"jobstatus:{JOB}:2"
        for markup in refresh
        if hasattr(markup, "inline_keyboard")
        for row in markup.inline_keyboard
        for b in row
    )


@pytest.mark.asyncio
async def test_scan_timeout_refresh_opens_same_owner_project_without_restarting_scan(harness):
    harness.service.config = BotConfig(SYNTHETIC_TOKEN, "synthetic-bot-key", wait_seconds=0, poll_seconds=0)
    harness.fixture.scan_states = ["running"]
    await harness.feed(callback=f"scan:{PROJECT}")
    refresh = [
        button.callback_data
        for method in harness.telegram.methods
        if isinstance(method, SendMessage) and hasattr(method.reply_markup, "inline_keyboard")
        for row in method.reply_markup.inline_keyboard
        for button in row
        if button.callback_data.startswith("scanrefresh:")
    ]
    assert refresh == [f"scanrefresh:{PROJECT}"]
    await harness.feed(callback=refresh[0])
    assert harness.fixture.calls[-1].url.path == f"/api/projects/{PROJECT}"
    assert (
        sum(request.method == "POST" and request.url.path.endswith("/scan") for request in harness.fixture.calls) == 1
    )
    assert any("Зависимостей: <b>1</b>" in value for value in harness.telegram.texts)


@pytest.mark.asyncio
async def test_project_awaiting_first_scan_exposes_refresh_instead_of_unavailable_report(harness):
    harness.fixture.project["latest_scan"] = {"id": SCAN, "status": "running"}
    await harness.feed(callback=f"project:{PROJECT}")
    card = next(method for method in harness.telegram.methods if isinstance(method, SendMessage))
    actions = [button.callback_data for row in card.reply_markup.inline_keyboard for button in row]
    assert f"scanrefresh:{PROJECT}" in actions
    assert f"scan:{PROJECT}" not in actions
    assert f"report:{PROJECT}" not in actions
    assert f"strategies:{PROJECT}" not in actions
    assert "продолжится" in card.text


@pytest.mark.asyncio
async def test_completed_deferred_fixlab_keeps_download_available(harness):
    harness.service.config = BotConfig(SYNTHETIC_TOKEN, "synthetic-bot-key", wait_seconds=0, poll_seconds=0)
    harness.fixture.job_states = ["running"]
    await harness.feed(callback=f"fix:{PROJECT}:1")
    assert not any(isinstance(method, SendDocument) for method in harness.telegram.methods)
    harness.fixture.job_states = ["succeeded"]
    await harness.feed(callback=f"jobstatus:{JOB}:1")
    documents = [method for method in harness.telegram.methods if isinstance(method, SendDocument)]
    assert len(documents) == 1
    assert len(json.loads(documents[0].document.data)["strategies"]) == 3


@pytest.mark.asyncio
async def test_empty_project_list_provides_working_example_without_creating_project(harness):
    harness.fixture.deleted = 1
    await harness.feed(text="/projects")
    example = next(
        button.callback_data
        for method in harness.telegram.methods
        if isinstance(method, SendMessage) and hasattr(method.reply_markup, "inline_keyboard")
        for row in method.reply_markup.inline_keyboard
        for button in row
        if button.callback_data == "example"
    )
    await harness.feed(callback=example)
    assert any(isinstance(method, SendDocument) for method in harness.telegram.methods)
    assert not any(
        request.method == "POST" and request.url.path == "/api/projects" for request in harness.fixture.calls
    )


@pytest.mark.asyncio
async def test_previous_telegram_reply_keyboard_still_opens_projects(harness):
    await harness.feed(text="📁 Мои проекты")
    assert harness.fixture.calls[-1].url.path == "/api/projects"
    assert any("Мои проекты" in value for value in harness.telegram.texts)


@pytest.mark.asyncio
async def test_network_errors_do_not_expose_secret_urls():
    def failure(request):
        raise httpx.ConnectError("private-token-sensitive-url", request=request)

    api = ApiClient("http://localhost:8000", "secret-key", transport=httpx.MockTransport(failure))
    with pytest.raises(ApiError) as caught:
        await api.identity(USER)
    assert "secret" not in str(caught.value)
    await api.close()


def test_config_repr_and_unknown_metrics_are_safe():
    config = BotConfig("private-token", "private-key")
    assert "private-token" not in repr(config) and "private-key" not in repr(config)
    finding = finding_summary({"id": "<x>", "cvss": None, "epss": None, "fixed_versions": []})
    assert "&lt;x&gt;" in finding and "нет данных" in finding


@pytest.mark.asyncio
async def test_navigation_is_available_while_scan_is_waiting(harness, monkeypatch):
    waiting = asyncio.Event()
    release = asyncio.Event()

    async def slow_scan(*args, **kwargs):
        waiting.set()
        await release.wait()

    monkeypatch.setattr(harness.service, "wait_scan", slow_scan)
    scan_task = asyncio.create_task(harness.feed(callback=f"scan:{PROJECT}"))
    await asyncio.wait_for(waiting.wait(), timeout=1)
    try:
        await asyncio.wait_for(harness.feed(text="/projects"), timeout=1)
        assert any("Мои проекты" in result for result in harness.telegram.texts)
    finally:
        release.set()
        await scan_task


@pytest.mark.asyncio
async def test_public_https_report_url_appears_without_authentication_token(harness):
    harness.service.config = BotConfig(SYNTHETIC_TOKEN, "synthetic-bot-key", web_url="https://paxveil.example.org")
    await harness.feed(callback=f"report:{PROJECT}")
    assert any(f"https://paxveil.example.org/app/projects/{PROJECT}" in s for s in harness.telegram.texts)
    assert all("synthetic-session" not in s for s in harness.telegram.texts)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://localhost:3000",
        "https://localhost.",
        "https://127.0.0.1",
        "https://10.0.0.1",
        "https://192.168.0.2",
        "https://[::1]",
        "https://backend",
        "https://server.internal",
        "https://paxveil.local",
        "https://user:pass@example.org",
    ],
)
def test_private_web_urls_are_not_suggested_to_public_users(url):
    assert BotConfig(SYNTHETIC_TOKEN, "synthetic-bot-key", web_url=url).public_web_url is None


@pytest.mark.asyncio
async def test_environment_is_validated_saved_and_used_in_upload(harness):
    await harness.feed(text="/environment 3.15 windows")
    assert not harness.fixture.calls
    await harness.feed(text="/environment 3.12 windows")
    assert harness.fixture.settings["upload_python_version"] == "3.12"
    assert harness.fixture.settings["upload_platform"] == "windows"
    await harness.feed(text="/quiet off")
    assert harness.fixture.settings["upload_platform"] == "windows"
    await harness.feed(document={"file_name": "requirements.txt", "file_size": len(harness.telegram.content)})
    upload = next(r for r in harness.fixture.calls if r.method == "POST" and r.url.path == "/api/projects")
    assert b'name="python_version"\r\n\r\n3.12' in upload.content
    assert b'name="platform"\r\n\r\nwindows' in upload.content


@pytest.mark.asyncio
async def test_privacy_does_not_create_account_and_export_uses_owner_session(harness):
    await harness.feed(text="/privacy")
    assert not harness.fixture.calls
    assert any("не запускает код" in s for s in harness.telegram.texts)
    await harness.feed(text="/export")
    document = next(m for m in harness.telegram.methods if isinstance(m, SendDocument))
    exported = json.loads(document.document.data)
    assert exported["account"]["telegram_id"] == USER
    assert harness.fixture.calls[-1].headers["Authorization"] == "Bearer synthetic-session"


@pytest.mark.asyncio
async def test_account_deletion_requires_owner_bound_expiring_single_use_confirmation(harness):
    await harness.feed(callback="accountconfirm:0000000000000000")
    assert not harness.fixture.calls
    await harness.feed(text="/delete_account")
    nonce = harness.service._confirmations[(USER, "account")][0]
    assert any("веб-аккаунтом" in s for s in harness.telegram.texts)
    await harness.feed(callback=f"accountconfirm:{nonce}", actor=USER + 1)
    assert harness.fixture.account_deleted == 0
    await harness.feed(callback=f"accountconfirm:{nonce}")
    assert harness.fixture.account_deleted == 1
    assert USER not in harness.api._sessions
    await harness.feed(callback=f"accountconfirm:{nonce}")
    assert harness.fixture.account_deleted == 1


@pytest.mark.asyncio
async def test_account_deletion_expiry_prevents_backend_request(harness):
    await harness.feed(text="/delete_account")
    nonce = harness.service._confirmations[(USER, "account")][0]
    harness.service._confirmations[(USER, "account")] = (nonce, 0)
    await harness.feed(callback=f"accountconfirm:{nonce}")
    assert harness.fixture.account_deleted == 0


@pytest.mark.asyncio
async def test_blocked_chat_on_error_reply_does_not_escape_or_expose_api_error(harness, caplog):
    original = harness.telegram.make_request

    async def blocked(bot, method, timeout=None):
        if isinstance(method, SendMessage):
            raise TelegramForbiddenError(method=method, message="sensitive-token-bearing-path")
        return await original(bot, method, timeout)

    harness.telegram.make_request = blocked
    await harness.feed(callback=f"project:{OTHER_PROJECT}")
    assert "telegram_error_reply_failed" in caplog.text
    assert "sensitive-token" not in caplog.text


@pytest.mark.asyncio
async def test_telegram_rate_limit_does_not_repeat_committed_upload(harness, caplog):
    original = harness.telegram.make_request

    async def limited(bot, method, timeout=None):
        if isinstance(method, SendMessage):
            raise TelegramRetryAfter(method=method, message="sensitive-token-bearing-path", retry_after=30)
        return await original(bot, method, timeout)

    harness.telegram.make_request = limited
    await harness.feed(document={"file_name": "requirements.txt", "file_size": len(harness.telegram.content)})
    assert sum(r.method == "POST" and r.url.path == "/api/projects" for r in harness.fixture.calls) == 1
    assert "telegram_rate_limited" in caplog.text
    assert "sensitive-token" not in caplog.text


@pytest.mark.asyncio
async def test_quota_detail_is_allowlisted_but_arbitrary_backend_message_is_hidden():
    def quota(request):
        return httpx.Response(
            429, json={"detail": {"code": "active_job_limit", "message": "sensitive backend debug value"}}
        )

    api = ApiClient("http://localhost:8000", "synthetic-bot-key", transport=httpx.MockTransport(quota))
    with pytest.raises(ApiError) as caught:
        await api.identity(USER)
    assert "Дождитесь завершения" in str(caught.value)
    assert "sensitive" not in str(caught.value)
    await api.close()


@pytest.mark.asyncio
async def test_slow_user_identity_does_not_block_another_user():
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    counts: dict[int, int] = {}

    async def identity(request):
        user = json.loads(request.content)["telegram_id"]
        counts[user] = counts.get(user, 0) + 1
        if user == USER:
            first_started.set()
            await release_first.wait()
        return httpx.Response(200, json={"token": f"fixture-session-{user}", "user": {"id": str(user)}})

    api = ApiClient("http://localhost:8000", "synthetic-bot-key", transport=httpx.MockTransport(identity))
    first = asyncio.create_task(api.identity(USER))
    duplicate = asyncio.create_task(api.identity(USER))
    await asyncio.wait_for(first_started.wait(), timeout=1)
    try:
        other = await asyncio.wait_for(api.identity(USER + 1), timeout=1)
        assert other.user["id"] == str(USER + 1)
    finally:
        release_first.set()
        await asyncio.gather(first, duplicate)
        await api.close()
    assert counts == {USER: 1, USER + 1: 1}


@pytest.mark.asyncio
async def test_failed_resource_limit_is_actionable_but_unknown_error_is_not_exposed(harness):
    harness.fixture.scan_states = ["failed"]
    harness.fixture.scan_error = "Достигнут лимит хранения. Удалите ненужные проекты"
    await harness.feed(callback=f"scan:{PROJECT}")
    assert any("Удалите ненужные проекты" in s for s in harness.telegram.texts)
    harness.fixture.scan_error = "database driver error: sensitive-private-value"
    await harness.feed(callback=f"scan:{PROJECT}")
    assert all("sensitive-private-value" not in s for s in harness.telegram.texts)


@pytest.mark.asyncio
async def test_example_is_explicit_user_action_and_sends_only_public_manifest(harness):
    assert not harness.telegram.methods
    await harness.feed(text="/example")
    assert not harness.fixture.calls
    documents = [m for m in harness.telegram.methods if isinstance(m, SendDocument)]
    assert len(documents) == 1
    document = documents[0]
    assert document.document.filename == "requirements.txt"
    assert document.document.data == b"requests==2.31.0\n"
    assert "Пакеты не устанавливаются" in document.caption
    assert "актуальным источникам" in document.caption
    assert any(b.callback_data == "example_scan" for row in document.reply_markup.inline_keyboard for b in row)
    label = next(label for label, action in MENU.items() if action == "example")
    await harness.feed(text=label)
    assert not harness.fixture.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger", ["button", "forwarded_file"])
async def test_example_uses_standard_upload_owner_environment_and_persisted_scan(harness, trigger):
    harness.fixture.settings.update(upload_python_version="3.12", upload_platform="windows")
    harness.fixture.scan_states = ["queued", "completed"]
    await harness.feed(text="/example")
    if trigger == "button":
        await harness.feed(callback="example_scan")
    else:
        document = next(m for m in harness.telegram.methods if isinstance(m, SendDocument))
        harness.telegram.content = document.document.data
        await harness.feed(document={"file_name": "requirements.txt", "file_size": len(harness.telegram.content)})
    uploads = [r for r in harness.fixture.calls if r.method == "POST" and r.url.path == "/api/projects"]
    assert len(uploads) == 1
    upload = uploads[0]
    assert upload.headers["Authorization"] == "Bearer synthetic-session"
    assert b"requests==2.31.0\n" in upload.content
    assert b'name="python_version"\r\n\r\n3.12' in upload.content
    assert b'name="platform"\r\n\r\nwindows' in upload.content
    assert any(r.url.path == f"/api/scans/{SCAN}" for r in harness.fixture.calls)
    assert any("Зависимостей: <b>1</b>" in message for message in harness.telegram.texts)


def test_sdk_logging_redacts_credentials_in_messages_and_tracebacks():
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.addFilter(SecretFilter("fixture-private-token", "fixture-service-key"))
    logger = logging.getLogger("paxveil.synthetic.log-safety")
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    try:
        logger.warning("Failed request https://api.telegram.org/bot%s/getUpdates", "fixture-private-token")
        try:
            raise ValueError("SDK debug URL: fixture-private-token; key=fixture-service-key")
        except ValueError:
            logger.exception("Controlled SDK failure")
    finally:
        logger.removeHandler(handler)
        handler.close()
    assert "fixture-private-token" not in output.getvalue()
    assert "fixture-service-key" not in output.getvalue()
    assert "[redacted]" in output.getvalue()
