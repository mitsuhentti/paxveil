from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

ALLOWED_HOSTS = {
    "api.osv.dev",
    "pypi.org",
    "api.deps.dev",
    "api.first.org",
    "www.cisa.gov",
}
MAX_RESPONSE_BYTES = 32 * 1024 * 1024


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


class SourceError(RuntimeError):
    def __init__(self, source: str, message: str, status_code: int | None = None):
        self.source, self.status_code = source, status_code
        super().__init__(f"{source}: {message}")


class SnapshotCache:
    """Durable TTL index plus content-addressed immutable public source snapshots."""

    def __init__(self, directory: str | Path | None = None):
        self.directory = Path(
            directory or os.getenv("PAXVEIL_CACHE_DIR", "runtime/cache")
        )
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "sources.sqlite3"
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    hash TEXT PRIMARY KEY, source TEXT NOT NULL,
                    fetched_at TEXT NOT NULL, body TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY, snapshot_hash TEXT NOT NULL,
                    expires_at REAL NOT NULL, fetched_at TEXT,
                    FOREIGN KEY(snapshot_hash) REFERENCES snapshots(hash)
                );
                CREATE INDEX IF NOT EXISTS ix_cache_expires ON cache(expires_at);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(cache)")}
            if "fetched_at" not in columns:
                try:
                    db.execute("ALTER TABLE cache ADD COLUMN fetched_at TEXT")
                except sqlite3.OperationalError as exc:
                    if "duplicate column" not in str(exc).lower():
                        raise
            db.execute(
                "UPDATE cache SET fetched_at=(SELECT fetched_at FROM snapshots WHERE snapshots.hash=cache.snapshot_hash) WHERE fetched_at IS NULL"
            )

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _get(self, key: str) -> dict | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT s.body,COALESCE(c.fetched_at,s.fetched_at),s.hash,c.expires_at FROM cache c JOIN snapshots s ON s.hash=c.snapshot_hash WHERE c.key=?",
                (key,),
            ).fetchone()
        if not row:
            return None
        return {
            "data": json.loads(row[0]),
            "fetched_at": row[1],
            "snapshot_hash": row[2],
            "fresh": row[3] > time.time(),
        }

    async def get(self, key: str) -> dict | None:
        return await asyncio.to_thread(self._get, key)

    def _put(self, key: str, source: str, data: dict, ttl: int) -> dict:
        body = json.dumps(
            data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        digest = hashlib.sha256(body.encode()).hexdigest()
        fetched_at = utcnow()
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO snapshots(hash,source,fetched_at,body) VALUES (?,?,?,?)",
                (digest, source, fetched_at, body),
            )
            db.execute(
                "INSERT INTO cache(key,snapshot_hash,expires_at,fetched_at) VALUES (?,?,?,?) ON CONFLICT(key) DO UPDATE SET snapshot_hash=excluded.snapshot_hash,expires_at=excluded.expires_at,fetched_at=excluded.fetched_at",
                (key, digest, time.time() + ttl, fetched_at),
            )
        return {"fetched_at": fetched_at, "snapshot_hash": digest}

    async def put(self, key: str, source: str, data: dict, ttl: int) -> dict:
        return await asyncio.to_thread(self._put, key, source, data, ttl)


class Sources:
    def __init__(
        self,
        *,
        cache: SnapshotCache | None = None,
        refresh: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.cache = cache or SnapshotCache()
        self.refresh = refresh
        self.records: list[dict] = []
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(20, connect=8),
            follow_redirects=False,
            transport=transport,
            trust_env=True,
            headers={
                "User-Agent": "PAXVEIL/1.0 (+https://github.com; public vulnerability metadata)",
                "Accept": "application/json",
            },
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=8),
        )
        self._semaphore = asyncio.Semaphore(6)
        self._limits: dict[str, asyncio.Lock] = {}
        self._next: dict[str, float] = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()

    def _record(self, name: str, status: str, key: str, **extra):
        self.records.append(
            {"name": name, "status": status, "request_hash": key, **extra}
        )

    async def _rate(self, host: str):
        lock = self._limits.setdefault(host, asyncio.Lock())
        async with lock:
            pause = max(0.0, self._next.get(host, 0.0) - time.monotonic())
            if pause:
                await asyncio.sleep(pause)
            self._next[host] = time.monotonic() + 0.2

    async def request(
        self,
        source: str,
        method: str,
        url: str,
        *,
        body: dict | None = None,
        ttl: int = 3600,
    ) -> dict:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username
            or parsed.password
            or parsed.port not in {None, 443}
        ):
            raise SourceError(source, "URL is outside the public source allowlist")
        key = hashlib.sha256(
            json.dumps([method, url, body], sort_keys=True).encode()
        ).hexdigest()
        cached = await self.cache.get(key)
        if cached and cached["fresh"] and not self.refresh:
            self._record(
                source,
                "cached",
                key,
                fetched_at=cached["fetched_at"],
                snapshot_hash=cached["snapshot_hash"],
            )
            return cached["data"]
        error = "Request failed"
        status_code = None
        for attempt in range(3):
            await self._rate(parsed.hostname)
            try:
                async with (
                    self._semaphore,
                    self._client.stream(method, url, json=body) as response,
                ):
                    status_code = response.status_code
                    if status_code == 429 or status_code >= 500:
                        delay = response.headers.get("retry-after", "")
                        retry_delay = (
                            min(float(delay), 10.0)
                            if delay.isdigit()
                            else min(0.5 * 2**attempt + random.uniform(0, 0.2), 5)
                        )
                        error = f"HTTP {status_code}"
                        retry = True
                    elif status_code != 200:
                        error = f"HTTP {status_code}"
                        retry = False
                    else:
                        chunks: list[bytes] = []
                        total = 0
                        async for chunk in response.aiter_bytes():
                            total += len(chunk)
                            if total > MAX_RESPONSE_BYTES:
                                raise SourceError(
                                    source, "Response exceeds 32 MiB limit"
                                )
                            chunks.append(chunk)
                        data = json.loads(b"".join(chunks))
                        if not isinstance(data, dict):
                            raise ValueError("Source JSON must be an object")
                        metadata = await self.cache.put(key, source, data, ttl)
                        self._record(source, "ok", key, **metadata)
                        return data
                if not retry:
                    break
                if attempt < 2:
                    await asyncio.sleep(retry_delay)
            except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
                error = type(exc).__name__
                if attempt < 2:
                    await asyncio.sleep(0.5 * 2**attempt)
        # Stale results are deliberately not silently substituted for current source data.
        self._record(
            source,
            "not_found" if status_code == 404 else "unavailable",
            key,
            fetched_at=None,
            error=error,
        )
        raise SourceError(source, error, status_code)

    async def osv_batch(
        self, dependencies: list[dict]
    ) -> dict[tuple[str, str], list[str]]:
        result: dict[tuple[str, str], list[str]] = {}
        for offset in range(0, len(dependencies), 100):
            batch = dependencies[offset : offset + 100]
            pending = [
                (
                    dep,
                    {
                        "package": {"name": dep["name"], "ecosystem": "PyPI"},
                        "version": dep["version"],
                    },
                )
                for dep in batch
            ]
            for _ in range(20):
                if not pending:
                    break
                response = await self.request(
                    "OSV",
                    "POST",
                    "https://api.osv.dev/v1/querybatch",
                    body={"queries": [query for _, query in pending]},
                )
                rows = response.get("results")
                if not isinstance(rows, list) or len(rows) != len(pending):
                    raise SourceError(
                        "OSV", "Batch response count does not match submitted versions"
                    )
                following = []
                for (dep, query), row in zip(pending, rows, strict=True):
                    if not isinstance(row, dict) or not isinstance(
                        row.get("vulns", []), list
                    ):
                        raise SourceError(
                            "OSV", "Invalid vulnerability query response shape"
                        )
                    key = (dep["name"], dep["version"])
                    ids = result.setdefault(key, [])
                    ids.extend(
                        v["id"]
                        for v in row.get("vulns", [])
                        if isinstance(v, dict) and isinstance(v.get("id"), str)
                    )
                    if row.get("next_page_token"):
                        following.append(
                            (dep, {**query, "page_token": row["next_page_token"]})
                        )
                pending = following
            if pending:
                raise SourceError("OSV", "Pagination exceeded safe request limit")
        return {key: list(dict.fromkeys(ids)) for key, ids in result.items()}

    async def advisory(self, advisory_id: str) -> dict:
        data = await self.request(
            "OSV", "GET", f"https://api.osv.dev/v1/vulns/{quote(advisory_id, safe='')}"
        )
        if (
            not isinstance(data.get("id"), str)
            or not isinstance(data.get("affected", []), list)
            or not isinstance(data.get("aliases", []), list)
        ):
            raise SourceError("OSV", "Invalid advisory response shape")
        return data

    async def release(self, name: str, version: str) -> dict:
        return await self.request(
            "PyPI",
            "GET",
            f"https://pypi.org/pypi/{quote(name, safe='')}/{quote(version, safe='')}/json",
            ttl=86400,
        )

    async def project(self, name: str) -> dict:
        return await self.request(
            "PyPI", "GET", f"https://pypi.org/pypi/{quote(name, safe='')}/json"
        )

    async def deps_requirements(self, name: str, version: str) -> dict:
        return await self.request(
            "deps.dev",
            "GET",
            f"https://api.deps.dev/v3/systems/PYPI/packages/{quote(name, safe='')}/versions/{quote(version, safe='')}:requirements",
            ttl=86400,
        )

    async def epss(self, cves: list[str]) -> dict[str, dict]:
        result = {}
        for offset in range(0, len(cves), 75):
            url = "https://api.first.org/data/v1/epss?cve=" + ",".join(
                cves[offset : offset + 75]
            )
            data = await self.request("FIRST EPSS", "GET", url, ttl=21600)
            if not isinstance(data.get("data"), list):
                raise SourceError("FIRST EPSS", "Invalid probability response shape")
            for item in data.get("data", []):
                try:
                    if (
                        not isinstance(item, dict)
                        or not 0 <= float(item["epss"]) <= 1
                        or not isinstance(item["cve"], str)
                    ):
                        raise ValueError("Invalid probability")
                except (TypeError, ValueError, KeyError) as exc:
                    raise SourceError("FIRST EPSS", "Invalid probability data") from exc
                result[item["cve"]] = item
        return result

    async def kev(self) -> set[str]:
        data = await self.request(
            "CISA KEV",
            "GET",
            "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
            ttl=21600,
        )
        if not isinstance(data.get("vulnerabilities"), list):
            raise SourceError(
                "CISA KEV", "Invalid exploited vulnerability catalog shape"
            )
        return {
            v["cveID"]
            for v in data.get("vulnerabilities", [])
            if isinstance(v, dict) and "cveID" in v
        }
