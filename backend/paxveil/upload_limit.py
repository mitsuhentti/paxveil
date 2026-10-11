from fastapi import HTTPException


class UploadLimitMiddleware:
    """Bound raw request streams before multipart parsing can spool to disk."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT"}:
            return await self.app(scope, receive, send)
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise HTTPException(413, "Максимальный размер файла — 1 МБ")
            return message

        await self.app(scope, limited_receive, send)
