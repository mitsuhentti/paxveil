from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from .parsers import parse

RESOLUTION_TIMEOUT = 90
MAX_OUTPUT = 2 * 1024 * 1024
PROXY_HOSTS = {"pypi.org", "files.pythonhosted.org"}


def run_bounded(
    command: list[str], directory: str, env: dict[str, str], cancelled: threading.Event
) -> tuple[int, bytes]:
    """File-backed output works under Windows sandboxes without named pipes."""
    path = Path(directory)
    stdout_path, stderr_path = path / "stdout.log", path / "stderr.log"
    process = None
    try:
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.Popen(
                command,
                cwd=directory,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            deadline = time.monotonic() + RESOLUTION_TIMEOUT
            while process.poll() is None:
                if cancelled.is_set() or time.monotonic() > deadline:
                    raise ResolutionError("Resolver timed out or was cancelled.")
                if (
                    stdout_path.stat().st_size > MAX_OUTPUT
                    or stderr_path.stat().st_size > MAX_OUTPUT
                ):
                    raise ResolutionError(
                        "Resolver diagnostic output exceeded safe limit."
                    )
                time.sleep(0.05)
            returncode = process.wait()
            if (
                stdout_path.stat().st_size > MAX_OUTPUT
                or stderr_path.stat().st_size > MAX_OUTPUT
            ):
                raise ResolutionError("Resolver diagnostic output exceeded safe limit.")
        return returncode, stderr_path.read_bytes()[-MAX_OUTPUT:]
    except OSError as exc:
        raise ResolutionError(
            f"Resolver could not start in this environment: {type(exc).__name__}."
        ) from exc
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=5)


class ResolutionError(RuntimeError):
    pass


def executable() -> str:
    sibling = Path(sys.executable).parent / ("uv.exe" if os.name == "nt" else "uv")
    if sibling.is_file():
        return str(sibling)
    path = shutil.which("uv")
    if not path:
        raise ResolutionError(
            "uv resolver is not installed; install backend requirements."
        )
    return path


@asynccontextmanager
async def index_proxy():
    """Permit only TLS tunnels to the two official PyPI distribution hosts.

    The resolver can see direct URLs in malicious wheel metadata. Its dedicated
    proxy blocks those destinations as well as loopback/private hosts.
    """
    blocked: set[str] = set()
    transferred = 0
    clients: set[asyncio.Task] = set()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        nonlocal transferred
        task = asyncio.current_task()
        clients.add(task)
        upstream = None
        try:
            header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 15)
            if len(header) > 8192:
                return
            request = (
                header.split(b"\r\n", 1)[0].decode("ascii", errors="replace").split()
            )
            host = request[1] if len(request) >= 2 else "invalid"
            if (
                len(request) != 3
                or request[0] != "CONNECT"
                or host not in {f"{name}:443" for name in PROXY_HOSTS}
            ):
                blocked.add(host)
                writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
                return
            upstream_reader, upstream = await asyncio.wait_for(
                asyncio.open_connection(host[:-4], 443), 15
            )
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()

            async def forward(
                source: asyncio.StreamReader, destination: asyncio.StreamWriter
            ):
                nonlocal transferred
                while chunk := await source.read(65536):
                    transferred += len(chunk)
                    if transferred > 150 * 1024 * 1024:
                        raise ResolutionError(
                            "Resolution exceeded network transfer limit."
                        )
                    destination.write(chunk)
                    await destination.drain()

            operations = [
                asyncio.create_task(forward(reader, upstream)),
                asyncio.create_task(forward(upstream_reader, writer)),
            ]
            _done, pending = await asyncio.wait(
                operations, return_when=asyncio.FIRST_COMPLETED
            )
            for operation in pending:
                operation.cancel()
            await asyncio.gather(*operations, return_exceptions=True)
        except (
            TimeoutError,
            OSError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            ResolutionError,
        ):
            pass
        finally:
            writer.close()
            if upstream:
                upstream.close()
            clients.discard(task)

    server = await asyncio.start_server(handle, "127.0.0.1", 0, limit=8192)
    port = server.sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}", blocked
    finally:
        server.close()
        await server.wait_closed()
        for client in list(clients):
            client.cancel()
        if clients:
            await asyncio.gather(*clients, return_exceptions=True)


async def resolve(requirements: list[str], python_version: str, platform: str) -> dict:
    # All input is reconstructed from validated Requirement objects. No uploaded
    # directives, URLs, local paths, configuration or build hooks are forwarded.
    safe_text = "\n".join(requirements) + "\n"
    parsed = parse("requirements.txt", safe_text.encode(), python_version, platform)
    if any(dep.status == "unsupported" for dep in parsed.dependencies):
        raise ResolutionError("Direct URL requirements cannot be simulated.")
    for line in requirements:
        if "@" in line or "\n" in line or "\r" in line or line.startswith("-"):
            raise ResolutionError("Only named PyPI requirements are accepted.")
    binary = executable()
    target = {
        "linux": "x86_64-unknown-linux-gnu",
        "windows": "x86_64-pc-windows-msvc",
        "darwin": "x86_64-apple-darwin",
    }[platform]
    with tempfile.TemporaryDirectory(prefix="paxveil-fixlab-") as directory:
        path = Path(directory)
        (path / "requirements.in").write_text(safe_text, encoding="utf-8")
        async with index_proxy() as (proxy, blocked):
            keep = {
                "SystemRoot",
                "SYSTEMROOT",
                "WINDIR",
                "PATH",
                "TEMP",
                "TMP",
                "COMSPEC",
                "PATHEXT",
            }
            env = {key: value for key, value in os.environ.items() if key in keep}
            env.update(
                {
                    "HTTPS_PROXY": proxy,
                    "HTTP_PROXY": proxy,
                    "ALL_PROXY": proxy,
                    "NO_PROXY": "",
                    "https_proxy": proxy,
                    "http_proxy": proxy,
                    "all_proxy": proxy,
                    "no_proxy": "",
                    "UV_NO_CONFIG": "1",
                    "UV_PYTHON_DOWNLOADS": "never",
                    "UV_CACHE_DIR": str(path / "cache"),
                    "UV_HTTP_TIMEOUT": "20",
                    "UV_HTTP_RETRIES": "1",
                }
            )
            command = [
                binary,
                "pip",
                "compile",
                "requirements.in",
                "--output-file",
                "resolved.txt",
                "--no-config",
                "--only-binary",
                ":all:",
                "--no-python-downloads",
                "--no-managed-python",
                "--default-index",
                "https://pypi.org/simple",
                "--python-version",
                python_version,
                "--python-platform",
                target,
                "--no-header",
                "--no-progress",
                "--no-annotate",
            ]
            cancelled = threading.Event()
            runner = asyncio.create_task(
                asyncio.to_thread(run_bounded, command, directory, env, cancelled)
            )
            try:
                returncode, stderr = await asyncio.shield(runner)
            except asyncio.CancelledError:
                cancelled.set()
                await asyncio.gather(runner, return_exceptions=True)
                raise
            if blocked:
                raise ResolutionError(
                    "Resolver metadata attempted an external destination; simulation blocked by the PyPI host allowlist."
                )
            if returncode:
                message = stderr.decode("utf-8", errors="replace")[-6000:]
                message = re.sub(r"https?://[^\s]+", "[index URL]", message)
                raise ResolutionError(
                    message.strip() or "No binary-only compatible resolution exists."
                )
            resolved = path / "resolved.txt"
            if not resolved.is_file() or resolved.stat().st_size > MAX_OUTPUT:
                raise ResolutionError(
                    "Resolver did not return a bounded requirements file."
                )
            content = resolved.read_bytes()
            checked = parse("requirements.txt", content, python_version, platform)
            if any(
                dep.version is None or dep.status == "unsupported"
                for dep in checked.dependencies
            ):
                raise ResolutionError(
                    "Resolver returned unsupported or unresolved dependencies."
                )
            return {
                "content": content,
                "dependencies": [dep.json() for dep in checked.dependencies],
                "resolver": "uv pip compile; binary metadata only; PyPI allowlist; no installation",
            }
