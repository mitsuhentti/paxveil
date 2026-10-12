from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import secrets
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, CallbackQuery, Message, TelegramObject

from .client import ApiClient, ApiError
from .config import BotConfig
from .presentation import (
    MENU,
    finding_summary,
    fix_summary,
    home_keyboard,
    keyboard,
    project_keyboard,
    report_summary,
    settings_summary,
    text,
)

logger = logging.getLogger(__name__)
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
CALLBACK = re.compile(
    rf"(?:home|settings|upload|fire|list:(?:projects|vulnerabilities|fixlab|watch):[0-9]{{1,5}}|"
    rf"(?:project|report|scan|strategies|delete):{UUID}|"
    rf"watch:{UUID}:[01]|fix:{UUID}:[012]|confirm:{UUID}:[0-9a-f]{{16}}|"
    rf"(?:scanstatus|jobstatus):{UUID}(?::[012])?)"
)
CVE = re.compile(r"CVE-[0-9]{4}-[0-9]{4,12}", re.IGNORECASE)
FILES = {"requirements.txt", "poetry.lock", "uv.lock"}
CATEGORIES = {"new", "priority", "fix", "exploitation", "status"}
COMPLETE = {"completed", "partial", "succeeded"}
ACTIVE = {"queued", "pending", "running", "retry"}


class BoundedBuffer(io.BytesIO):
    """Enforce the limit while streaming, even if Telegram metadata is wrong."""

    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit

    def write(self, chunk: bytes) -> int:
        if self.tell() + len(chunk) > self.limit:
            raise ValueError("File exceeds limit")
        return super().write(chunk)


class GuardMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self._rates: OrderedDict[int, tuple[float, float]] = OrderedDict()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        actor = getattr(event, "from_user", None)
        message = event.message if isinstance(event, CallbackQuery) else event
        chat = getattr(message, "chat", None)
        if not actor or not chat or chat.type != "private" or chat.id != actor.id:
            if isinstance(event, CallbackQuery):
                await event.answer(
                    "Откройте PAXVEIL Bot в личном чате.", show_alert=True
                )
            elif isinstance(event, Message):
                await event.answer(
                    "Работа с проектами доступна в личном чате PAXVEIL Bot."
                )
            return None
        now = time.monotonic()
        tokens, last = self._rates.get(actor.id, (8.0, now))
        tokens = min(8.0, tokens + (now - last) / 2)
        self._rates[actor.id] = (max(0.0, tokens - 1), now)
        self._rates.move_to_end(actor.id)
        while len(self._rates) > 4096:
            self._rates.popitem(last=False)
        if tokens < 1:
            if isinstance(event, CallbackQuery):
                await event.answer(
                    "Подождите немного перед следующим действием.", show_alert=True
                )
            else:
                await message.answer("Подождите немного перед следующим действием.")
            return None
        try:
            return await handler(event, data)
        except ApiError as exc:
            await message.answer(
                text(str(exc)), reply_markup=keyboard([[("Главное меню", "home")]])
            )
        except TelegramAPIError:
            # Telegram may reject a deleted chat/message; never log token-bearing URLs.
            logger.warning("telegram_request_failed")
        except Exception as exc:  # noqa: BLE001 -- isolate updates without logging credential-bearing errors
            logger.error("bot_handler_failed error_type=%s", type(exc).__name__)
            await message.answer(
                "Не удалось завершить действие. Откройте /projects, проверьте состояние и повторите."
            )
        return None


class BotService:
    def __init__(self, api: ApiClient, config: BotConfig):
        self.api = api
        self.config = config
        self._confirmations: OrderedDict[tuple[int, str], tuple[str, float]] = (
            OrderedDict()
        )

    def report_url(self, project_id: str, section: str = "") -> str:
        suffix = f"?tab={section}" if section else ""
        return f"{self.config.web_url}/app/projects/{project_id}{suffix}"

    async def home(self, message: Message) -> None:
        assert message.from_user is not None
        await self.api.identity(message.from_user.id)
        await message.answer(
            "<b>PAXVEIL Bot</b>\nПроверьте Python-зависимости, сравните обновления и включите Watch.\n"
            "Отправьте requirements.txt, poetry.lock или uv.lock до 1 МиБ.\n"
            "Для общего доступа к веб-проектам: Настройки → /link.",
            reply_markup=home_keyboard(),
        )

    async def list_projects(
        self, message: Message, user_id: int, mode: str = "projects", page: int = 0
    ) -> None:
        projects = await self.api.projects(user_id)
        if mode == "watch":
            projects = sorted(projects, key=lambda p: not p.get("watch"))
        if not projects:
            await message.answer(
                "Пока нет проектов. Отправьте файл зависимостей или свяжите веб-аккаунт командой /link.",
                reply_markup=keyboard(
                    [[("🔍 Загрузить файл", "upload"), ("Главное меню", "home")]]
                ),
            )
            return
        size = 6
        last_page = (len(projects) - 1) // size
        page = min(page, last_page)
        titles = {
            "projects": "Мои проекты",
            "watch": "Мониторинг",
            "fixlab": "FixLab · выберите проект",
            "vulnerabilities": "Уязвимости · выберите проект",
        }
        rows: list[list[tuple[str, str]]] = []
        for project in projects[page * size : (page + 1) * size]:
            action = (
                "strategies"
                if mode == "fixlab"
                else "report"
                if mode == "vulnerabilities"
                else "project"
            )
            marker = "🔔 " if project.get("watch") else ""
            rows.append(
                [
                    (
                        marker + str(project.get("name", "Проект"))[:50],
                        f"{action}:{project['id']}",
                    )
                ]
            )
        pages = []
        if page > 0:
            pages.append(("←", f"list:{mode}:{page - 1}"))
        if page < last_page:
            pages.append(("→", f"list:{mode}:{page + 1}"))
        if pages:
            rows.append(pages)
        rows.append([("Главное меню", "home")])
        await message.answer(
            f"<b>{titles[mode]}</b>\nПроектов: {len(projects)} · страница {page + 1}/{last_page + 1}",
            reply_markup=keyboard(rows),
        )

    async def show_project(
        self, message: Message, user_id: int, project_id: str
    ) -> None:
        project = await self.api.project(user_id, project_id)
        await message.answer(
            report_summary(project), reply_markup=project_keyboard(project)
        )

    async def show_report(
        self, message: Message, user_id: int, project_id: str
    ) -> None:
        project = await self.api.project(user_id, project_id)
        report = (project.get("latest_scan") or {}).get("report")
        await message.answer(
            report_summary(project), reply_markup=project_keyboard(project)
        )
        if not report:
            return
        findings = sorted(
            report.get("findings") or [],
            key=lambda f: f.get("priority") or 0,
            reverse=True,
        )
        for finding in findings[:3]:
            await message.answer(finding_summary(finding))
        await message.answer(
            f'Подробный отчёт: <a href="{text(self.report_url(project_id), 1000)}">открыть PAXVEIL</a>.\n'
            "В браузере войдите в связанный веб-аккаунт. Локальный адрес доступен на компьютере, где запущен PAXVEIL.",
        )
        payload = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
        if len(payload) <= 8 * 1_048_576:
            await message.answer_document(
                BufferedInputFile(
                    payload, filename=f"paxveil-report-{project_id}.json"
                ),
                caption="Полный отчёт; все данные получены API для вашего аккаунта.",
            )

    async def wait_scan(
        self, message: Message, user_id: int, scan_id: str, project_id: str
    ) -> None:
        deadline = time.monotonic() + self.config.wait_seconds
        last_status = None
        while True:
            scan = await self.api.request(user_id, "GET", f"scans/{scan_id}")
            status = scan.get("status", "unknown")
            if status in COMPLETE:
                await self.show_project(message, user_id, project_id)
                return
            if status == "failed":
                await message.answer(
                    "Сканирование не завершилось. Проверьте файл и повторите из меню проекта.",
                    reply_markup=keyboard(
                        [[("Открыть проект", f"project:{project_id}")]]
                    ),
                )
                return
            if status not in ACTIVE:
                raise ApiError(
                    "API вернул неизвестный статус сканирования. Обновите проект."
                )
            if last_status != status:
                await message.answer(f"Сканирование: <code>{text(status, 40)}</code>.")
                last_status = status
            if time.monotonic() >= deadline:
                await message.answer(
                    "Сканирование продолжается в очереди. Можно обновить состояние или открыть проект позже.",
                    reply_markup=keyboard(
                        [
                            [("Обновить состояние", f"scanstatus:{scan_id}")],
                            [("Открыть проект", f"project:{project_id}")],
                        ]
                    ),
                )
                return
            await asyncio.sleep(self.config.poll_seconds)

    async def wait_job(
        self, message: Message, user_id: int, job_id: str, strategy: int | None = None
    ) -> dict[str, Any] | None:
        deadline = time.monotonic() + self.config.wait_seconds
        last_status = None
        while True:
            job = await self.api.request(user_id, "GET", f"jobs/{job_id}")
            status = job.get("status", "unknown")
            if status in COMPLETE:
                return job.get("result") or {}
            if status == "failed":
                await message.answer(
                    "Задание завершилось с ошибкой. Откройте проект и повторите запрос позже."
                )
                return None
            if status not in ACTIVE:
                raise ApiError(
                    "API вернул неизвестный статус задания. Обновите проект."
                )
            if last_status != status:
                await message.answer(f"Задание: <code>{text(status, 40)}</code>.")
                last_status = status
            if time.monotonic() >= deadline:
                suffix = f":{strategy}" if strategy is not None else ""
                await message.answer(
                    "Задание продолжает выполняться. Нажмите кнопку, чтобы проверить результат.",
                    reply_markup=keyboard(
                        [
                            [("Обновить состояние", f"jobstatus:{job_id}{suffix}")],
                            [("Главное меню", "home")],
                        ]
                    ),
                )
                return None
            await asyncio.sleep(self.config.poll_seconds)

    async def upload(self, message: Message, bot: Bot) -> None:
        assert message.from_user and message.document
        doc = message.document
        filename = doc.file_name or ""
        if filename not in FILES:
            await message.answer(
                "Поддерживаются только requirements.txt, poetry.lock и uv.lock. Переименовывание другого формата не делает его допустимым."
            )
            return
        if doc.file_size is not None and (
            doc.file_size <= 0 or doc.file_size > self.config.max_file_bytes
        ):
            await message.answer("Отправьте непустой файл размером до 1 МиБ.")
            return
        telegram_file = await bot.get_file(doc.file_id)
        if not telegram_file.file_path:
            raise ApiError("Telegram не вернул файл. Отправьте его заново.")
        if (
            telegram_file.file_size is not None
            and telegram_file.file_size > self.config.max_file_bytes
        ):
            await message.answer("Размер файла превышает 1 МиБ.")
            return
        buffer = BoundedBuffer(self.config.max_file_bytes)
        try:
            await bot.download_file(
                telegram_file.file_path,
                destination=buffer,
                timeout=30,
                chunk_size=65536,
            )
        except ValueError:
            await message.answer("Размер файла превышает 1 МиБ.")
            return
        content = buffer.getvalue()
        buffer.close()
        if not content or b"\x00" in content:
            await message.answer("Требуется непустой текстовый файл зависимостей.")
            return
        project = await self.api.upload(
            message.from_user.id,
            filename,
            content,
            (message.caption or filename).strip()[:80],
        )
        await message.answer(
            "Проект сохранён. Анализ поставлен в очередь. Среда: Python 3.11 / Linux; другую среду выберите в веб-интерфейсе."
        )
        latest = project.get("latest_scan") or {}
        if latest.get("id"):
            await self.wait_scan(
                message, message.from_user.id, str(latest["id"]), str(project["id"])
            )
        else:
            await self.show_project(message, message.from_user.id, str(project["id"]))

    async def strategies(self, message: Message, user_id: int, project_id: str) -> None:
        project = await self.api.project(user_id, project_id)
        if not (project.get("latest_scan") or {}).get("report"):
            await message.answer(
                "Для FixLab нужен завершённый отчёт.",
                reply_markup=project_keyboard(project),
            )
            return
        await message.answer(
            f"<b>FixLab · {text(project.get('name'), 80)}</b>\nВыберите стратегию. Модель проверит варианты без установки пакетов.",
            reply_markup=keyboard(
                [
                    [("Minimal Change", f"fix:{project_id}:0")],
                    [("Balanced", f"fix:{project_id}:1")],
                    [("Maximum Coverage", f"fix:{project_id}:2")],
                    [("← Проект", f"project:{project_id}")],
                ]
            ),
        )

    async def run_fix(
        self, message: Message, user_id: int, project_id: str, choice: int
    ) -> None:
        project = await self.api.project(user_id, project_id)
        scan = project.get("latest_scan") or {}
        if not scan.get("report"):
            raise ApiError("Для FixLab нужен завершённый отчёт.")
        job = await self.api.request(user_id, "POST", f"scans/{scan['id']}/fixlab")
        result = await self.wait_job(message, user_id, str(job["id"]), choice)
        if result is not None:
            await self.show_fix_result(message, result, choice)
            await message.answer(
                f'<a href="{text(self.report_url(project_id, "fixlab"), 1000)}">Подробное сравнение FixLab</a>',
                reply_markup=project_keyboard(project),
            )

    async def show_fix_result(
        self, message: Message, result: dict[str, Any], choice: int
    ) -> None:
        strategies = result.get("strategies") or []
        if choice >= len(strategies):
            raise ApiError(
                "Не удалось получить выбранную стратегию. Откройте веб-отчёт."
            )
        await message.answer(
            fix_summary(strategies[choice], result.get("limitations") or [])
        )

    async def fire(self, message: Message, user_id: int, argument: str) -> None:
        cve = argument.strip().upper()
        if not CVE.fullmatch(cve):
            await message.answer(
                "Отправьте команду с одним идентификатором: <code>/fire CVE-2024-35195</code>."
            )
            return
        await message.answer(
            f"Fire Drill: проверяю <code>{text(cve)}</code> по реальным источникам и вашим сохранённым отчётам."
        )
        result = await self.api.request(user_id, "POST", "fire", json={"cve": cve})
        matches = result.get("matches") or []
        lines = [
            f"<b>Fire Drill · {text(cve)}</b>",
            f"Статус источника: <code>{text(result.get('status', 'unknown'), 60)}</code>",
        ]
        if matches:
            lines.append(f"Потенциально затронутых записей: {len(matches)}")
            for match in matches[:6]:
                lines.append(
                    f"• {text(match.get('project_name'), 80)}: <code>{text(match.get('package'), 80)}=={text(match.get('version'), 60)}</code> · {text(match.get('status'), 50)}"
                )
        else:
            lines.append(
                "Совпадений в сохранённых отчётах не найдено. Достоверность зависит от состояния источников и свежести отчётов."
            )
        for limitation in (result.get("limitations") or [])[:3]:
            lines.append("⚠️ " + text(limitation, 350))
        lines.append("Совпадение версии не доказывает эксплуатацию в приложении.")
        rows = [
            [(str(m.get("project_name", "Проект"))[:50], f"project:{m['project_id']}")]
            for m in matches[:6]
            if m.get("project_id")
        ]
        rows.append([("Главное меню", "home")])
        await message.answer("\n".join(lines), reply_markup=keyboard(rows))

    async def settings(self, message: Message, user_id: int) -> None:
        settings = await self.api.request(user_id, "GET", "settings")
        categories = settings.get("categories") or []
        await message.answer(
            settings_summary(settings)
            + "\nАктивные категории: "
            + text(", ".join(categories), 180),
            reply_markup=keyboard([[("Главное меню", "home")]]),
        )

    async def configure(
        self, message: Message, user_id: int, command: str, argument: str
    ) -> None:
        args = argument.split()
        patch: dict[str, Any]
        usage = {
            "timezone": "/timezone Europe/Moscow",
            "quiet": "/quiet 22:00 08:00 или /quiet off",
            "priority": "/priority 60 (от 0 до 100)",
            "digest": "/digest on или /digest off",
            "category": "/category new off (new, priority, fix, exploitation, status)",
        }
        try:
            if command == "timezone":
                if len(args) != 1 or len(args[0]) > 80:
                    raise ValueError
                ZoneInfo(args[0])
                patch = {"timezone": args[0]}
            elif command == "quiet":
                if args == ["off"]:
                    patch = {"quiet_start": None, "quiet_end": None}
                else:
                    if (
                        len(args) != 2
                        or not all(
                            re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", arg)
                            for arg in args
                        )
                        or args[0] == args[1]
                    ):
                        raise ValueError
                    patch = {"quiet_start": args[0], "quiet_end": args[1]}
            elif command == "priority":
                if (
                    len(args) != 1
                    or not args[0].isdigit()
                    or not 0 <= int(args[0]) <= 100
                ):
                    raise ValueError
                patch = {"minimum_priority": int(args[0])}
            elif command == "digest":
                if len(args) != 1 or args[0] not in {"on", "off"}:
                    raise ValueError
                patch = {"digest": args[0] == "on"}
            else:
                if (
                    len(args) != 2
                    or args[0] not in CATEGORIES
                    or args[1] not in {"on", "off"}
                ):
                    raise ValueError
                current = await self.api.request(user_id, "GET", "settings")
                categories = set(current.get("categories") or [])
                if args[1] == "on":
                    categories.add(args[0])
                else:
                    categories.discard(args[0])
                patch = {"categories": sorted(categories)}
        except (ValueError, ZoneInfoNotFoundError):
            await message.answer("Формат: <code>" + text(usage[command]) + "</code>")
            return
        current = await self.api.request(user_id, "GET", "settings")
        editable = {
            key: current.get(key)
            for key in [
                "timezone",
                "quiet_start",
                "quiet_end",
                "minimum_priority",
                "digest",
                "categories",
            ]
        }
        editable.update(patch)
        await self.api.request(user_id, "PUT", "settings", json=editable)
        await self.settings(message, user_id)

    async def delete_prompt(
        self, message: Message, user_id: int, project_id: str
    ) -> None:
        project = await self.api.project(user_id, project_id)
        nonce = secrets.token_hex(8)
        self._confirmations[(user_id, project_id)] = (nonce, time.monotonic() + 120)
        self._confirmations.move_to_end((user_id, project_id))
        while len(self._confirmations) > 1024:
            self._confirmations.popitem(last=False)
        await message.answer(
            f"Удалить <b>{text(project.get('name'), 80)}</b> вместе с историей и подпиской? Подтверждение действует 2 минуты.",
            reply_markup=keyboard(
                [
                    [("Удалить", f"confirm:{project_id}:{nonce}")],
                    [("Отмена", f"project:{project_id}")],
                ]
            ),
        )

    async def confirm_delete(
        self, message: Message, user_id: int, project_id: str, nonce: str
    ) -> None:
        confirmation = self._confirmations.get((user_id, project_id))
        if (
            not confirmation
            or confirmation[1] < time.monotonic()
            or not secrets.compare_digest(confirmation[0], nonce)
        ):
            await message.answer(
                "Подтверждение отсутствует или истекло. Откройте проект и нажмите «Удалить» снова."
            )
            return
        self._confirmations.pop((user_id, project_id), None)
        await self.api.request(user_id, "DELETE", f"projects/{project_id}")
        await message.answer("Проект удалён, мониторинг отключён.")
        await self.list_projects(message, user_id)

    async def callback(self, callback: CallbackQuery) -> None:
        payload = callback.data or ""
        if len(payload.encode("utf-8")) > 64 or not CALLBACK.fullmatch(payload):
            await callback.answer(
                "Кнопка недействительна. Откройте /start.", show_alert=True
            )
            return
        await callback.answer()
        assert isinstance(callback.message, Message)
        message, user_id = callback.message, callback.from_user.id
        parts = payload.split(":")
        action = parts[0]
        if action == "home":
            # Callback messages are authored by the bot, so use the callback actor.
            await self.api.identity(user_id)
            await message.answer(
                "Выберите действие в меню PAXVEIL Bot.", reply_markup=home_keyboard()
            )
        elif action in {"upload", "fire"}:
            await message.answer(
                "Отправьте requirements.txt, poetry.lock или uv.lock до 1 МиБ. Подпись к файлу станет именем проекта."
                if action == "upload"
                else "Отправьте <code>/fire CVE-2024-35195</code> для проверки конкретного CVE."
            )
        elif action == "settings":
            await self.settings(message, user_id)
        elif action == "list":
            await self.list_projects(message, user_id, parts[1], int(parts[2]))
        elif action == "project":
            await self.show_project(message, user_id, parts[1])
        elif action == "report":
            await self.show_report(message, user_id, parts[1])
        elif action == "strategies":
            await self.strategies(message, user_id, parts[1])
        elif action == "fix":
            await self.run_fix(message, user_id, parts[1], int(parts[2]))
        elif action == "watch":
            await self.api.request(
                user_id,
                "PUT",
                f"projects/{parts[1]}/watch",
                json={"enabled": parts[2] == "1"},
            )
            await self.show_project(message, user_id, parts[1])
        elif action == "scan":
            job = await self.api.request(user_id, "POST", f"projects/{parts[1]}/scan")
            await self.wait_scan(message, user_id, str(job["scan_id"]), parts[1])
        elif action == "delete":
            await self.delete_prompt(message, user_id, parts[1])
        elif action == "confirm":
            await self.confirm_delete(message, user_id, parts[1], parts[2])
        elif action == "scanstatus":
            scan = await self.api.request(user_id, "GET", f"scans/{parts[1]}")
            await message.answer(
                f"Сканирование: <code>{text(scan.get('status'), 40)}</code>. Откройте проект в /projects для отчёта."
            )
        elif action == "jobstatus":
            result = await self.wait_job(
                message, user_id, parts[1], int(parts[2]) if len(parts) == 3 else None
            )
            if result is not None:
                if len(parts) == 3:
                    await self.show_fix_result(message, result, int(parts[2]))
                else:
                    await message.answer(
                        "Задание завершено. Отчёт доступен в /projects."
                    )


def build_dispatcher(service: BotService) -> Dispatcher:
    # Waiting for a persisted scan must not lock navigation in the user's chat.
    dispatcher = Dispatcher(disable_fsm=True)
    router = Router(name="paxveil_bot")
    guard = GuardMiddleware()
    router.message.outer_middleware(guard)
    router.callback_query.outer_middleware(guard)

    @router.message(Command("start", "help"))
    async def start(message: Message) -> None:
        await service.home(message)

    @router.message(Command("projects", "watch", "fixlab", "vulnerabilities"))
    async def projects(message: Message, command: CommandObject) -> None:
        assert message.from_user
        await service.list_projects(message, message.from_user.id, command.command)

    @router.message(Command("fire"))
    async def fire(message: Message, command: CommandObject) -> None:
        assert message.from_user
        await service.fire(message, message.from_user.id, command.args or "")

    @router.message(Command("settings"))
    async def settings(message: Message) -> None:
        assert message.from_user
        await service.settings(message, message.from_user.id)

    @router.message(Command("timezone", "quiet", "priority", "digest", "category"))
    async def configure(message: Message, command: CommandObject) -> None:
        assert message.from_user
        await service.configure(
            message, message.from_user.id, command.command, command.args or ""
        )

    @router.message(Command("link"))
    async def link(message: Message, command: CommandObject) -> None:
        assert message.from_user
        code = (command.args or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,128}", code):
            await message.answer(
                "Откройте Настройки → Telegram в PAXVEIL, получите код и отправьте <code>/link КОД</code>. Код одноразовый и действует 10 минут."
            )
            return
        await service.api.link(message.from_user.id, code)
        # Remove the visible code where Telegram permits it. No secret is echoed.
        try:
            await message.delete()
        except TelegramAPIError:
            pass
        await message.answer(
            "Telegram связан с веб-аккаунтом. Теперь проекты и настройки общие.",
            reply_markup=home_keyboard(),
        )

    @router.message(F.document)
    async def upload(message: Message, bot: Bot) -> None:
        await service.upload(message, bot)

    @router.callback_query()
    async def callback(callback: CallbackQuery) -> None:
        await service.callback(callback)

    @router.message()
    async def menu(message: Message) -> None:
        assert message.from_user
        action = MENU.get(message.text or "")
        if action in {"projects", "watch", "fixlab", "vulnerabilities"}:
            await service.list_projects(message, message.from_user.id, action)
        elif action == "settings":
            await service.settings(message, message.from_user.id)
        elif action == "fire":
            await message.answer("Отправьте <code>/fire CVE-2024-35195</code>.")
        elif action == "upload":
            await message.answer(
                "Отправьте requirements.txt, poetry.lock или uv.lock до 1 МиБ. Подпись к файлу станет именем проекта. Файлы хранятся в вашем аккаунте; удаление доступно в меню проекта."
            )
        else:
            await message.answer(
                "Выберите действие в меню или отправьте файл зависимостей.",
                reply_markup=home_keyboard(),
            )

    dispatcher.include_router(router)
    return dispatcher
