from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

import httpx


class ApiError(Exception):
    """A safe user-facing API failure, without credentials or transport URLs."""

    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


@dataclass
class Session:
    token: str = field(repr=False)
    user: dict[str, Any]
    created: float = field(default_factory=time.monotonic)


class ApiClient:
    """The bot never queries PostgreSQL or trusts callback IDs for authorization."""

    def __init__(
        self,
        api_url: str,
        bot_key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._bot_key = bot_key
        self._http = httpx.AsyncClient(
            base_url=api_url.rstrip("/") + "/api/",
            timeout=httpx.Timeout(45.0, connect=10.0),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )
        self._sessions: OrderedDict[int, Session] = OrderedDict()
        # Bounded lock stripes collapse duplicate auth for one user without
        # making every new user wait for an unrelated slow identity request.
        self._identity_locks = [asyncio.Lock() for _ in range(64)]

    async def close(self) -> None:
        self._sessions.clear()
        await self._http.aclose()

    def forget(self, telegram_id: int) -> None:
        self._sessions.pop(telegram_id, None)

    async def _send(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.HTTPError:
            raise ApiError("PAXVEIL API временно недоступен. Попробуйте позже.") from None
        if not response.is_success:
            messages = {
                400: "Запрос не принят. Проверьте данные и повторите.",
                401: "Сессия истекла. Повторите /start.",
                403: "Доступ к этому объекту запрещён.",
                404: "Объект не найден или вам недоступен.",
                409: "Действие уже выполняется или данные изменились. Обновите список.",
                413: "Размер файла превышает 1 МиБ.",
                422: "Неверный формат данных. Проверьте файл или параметры.",
                429: "Слишком много запросов. Подождите немного.",
            }
            message = messages.get(
                response.status_code,
                "Сервис не смог завершить запрос. Попробуйте позже.",
            )
            # Display only an explicit allowlist of quota details, never arbitrary
            # backend errors, which can include exception paths or user content.
            if response.status_code in {409, 413, 429}:
                try:
                    detail = response.json().get("detail")
                except (ValueError, AttributeError):
                    detail = None
                code = detail.get("code") if isinstance(detail, dict) else detail
                quota_messages = {
                    "project_limit": "Достигнут лимит проектов. Удалите ненужный проект и повторите.",
                    "active_job_limit": "Дождитесь завершения текущих проверок перед новым запросом.",
                    "analysis_limit": "Лимит проверок на час исчерпан. Повторите позже.",
                    "storage_limit": "Достигнут лимит хранения файлов. Удалите ненужные проекты и повторите.",
                    "fire_limit": "Лимит проверок CVE на час исчерпан. Повторите позже.",
                    "export_limit": "Лимит выгрузок на час исчерпан. Повторите позже.",
                    "export_size_limit": "Выгрузка превышает 40 МиБ. Удалите ненужные проекты и повторите выгрузку.",
                }
                if isinstance(code, str) and code in quota_messages:
                    message = quota_messages[code]
            raise ApiError(message, response.status_code)
        if response.status_code == 204:
            return None
        try:
            return response.json()
        except ValueError:
            raise ApiError("API вернул некорректный ответ. Попробуйте позже.") from None

    def _remember(self, telegram_id: int, data: dict[str, Any]) -> Session:
        token = data.get("token")
        user = data.get("user")
        if not isinstance(token, str) or not token or not isinstance(user, dict):
            raise ApiError("Не удалось получить защищённую сессию.")
        session = Session(token, user)
        self._sessions[telegram_id] = session
        self._sessions.move_to_end(telegram_id)
        while len(self._sessions) > 512:
            self._sessions.popitem(last=False)
        return session

    async def identity(self, telegram_id: int, *, refresh: bool = False) -> Session:
        if telegram_id <= 0:
            raise ApiError("Требуется личный Telegram-аккаунт.")
        async with self._identity_locks[telegram_id % len(self._identity_locks)]:
            cached = self._sessions.get(telegram_id)
            if cached and not refresh and time.monotonic() - cached.created < 3600:
                self._sessions.move_to_end(telegram_id)
                return cached
            data = await self._send(
                "POST",
                "bot/identity",
                json={"telegram_id": telegram_id},
                headers={"X-Bot-Key": self._bot_key},
            )
            return self._remember(telegram_id, data)

    async def link(self, telegram_id: int, code: str) -> Session:
        data = await self._send(
            "POST",
            "bot/link",
            json={"telegram_id": telegram_id, "code": code},
            headers={"X-Bot-Key": self._bot_key},
        )
        return self._remember(telegram_id, data)

    async def request(self, telegram_id: int, method: str, path: str, **kwargs: Any) -> Any:
        session = await self.identity(telegram_id)
        try:
            return await self._send(
                method,
                path,
                headers={"Authorization": f"Bearer {session.token}"},
                **kwargs,
            )
        except ApiError as exc:
            if exc.status != 401:
                raise
        session = await self.identity(telegram_id, refresh=True)
        return await self._send(method, path, headers={"Authorization": f"Bearer {session.token}"}, **kwargs)

    async def projects(self, telegram_id: int) -> list[dict[str, Any]]:
        return await self.request(telegram_id, "GET", "projects")

    async def project(self, telegram_id: int, project_id: str) -> dict[str, Any]:
        return await self.request(telegram_id, "GET", f"projects/{project_id}")

    async def upload(
        self,
        telegram_id: int,
        filename: str,
        content: bytes,
        name: str,
        *,
        python_version: str = "3.11",
        platform: str = "linux",
    ) -> dict[str, Any]:
        return await self.request(
            telegram_id,
            "POST",
            "projects",
            data={"name": name, "python_version": python_version, "platform": platform},
            files={"file": (filename, content, "text/plain")},
        )
