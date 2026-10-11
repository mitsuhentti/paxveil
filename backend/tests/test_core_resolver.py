import asyncio
import sys
import threading

import pytest

from paxveil.core.resolver import ResolutionError, index_proxy, resolve, run_bounded


@pytest.mark.asyncio
async def test_proxy_blocks_external_and_private_destinations():
    async with index_proxy() as (proxy, blocked):
        port = int(proxy.rsplit(":", 1)[1])
        for host in [
            "127.0.0.1:443",
            "example.com:443",
            "pypi.org:8443",
            "files.pythonhosted.org.evil.test:443",
        ]:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(f"CONNECT {host} HTTP/1.1\r\nHost: {host}\r\n\r\n".encode())
            await writer.drain()
            assert b"403" in await reader.read(1000)
            writer.close()
        assert len(blocked) == 4


@pytest.mark.asyncio
async def test_resolver_rejects_uploaded_url_options():
    with pytest.raises((ResolutionError, ValueError)):
        await resolve(["evil @ https://127.0.0.1/evil.whl"], "3.11", "linux")
    with pytest.raises((ResolutionError, ValueError)):
        await resolve(["--index-url https://example.com"], "3.11", "linux")


def test_subprocess_file_backed_diagnostics_work_without_named_pipes(tmp_path):
    import os

    code, stderr = run_bounded(
        [sys.executable, "-c", "import sys; print('diagnostic',file=sys.stderr)"],
        str(tmp_path),
        dict(os.environ),
        threading.Event(),
    )
    assert code == 0
    assert stderr.strip() == b"diagnostic"


def test_subprocess_cancellation_stops_process(tmp_path):
    import os

    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(ResolutionError, match="cancelled"):
        run_bounded(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            str(tmp_path),
            dict(os.environ),
            cancelled,
        )
