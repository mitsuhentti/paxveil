import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import httpx
import pytest

from paxveil.core.sources import SnapshotCache, SourceError, Sources


@pytest.mark.asyncio
async def test_identical_refetch_updates_cache_time_and_preserves_snapshot(tmp_path, monkeypatch):
    times = iter(["2026-10-09T00:00:00+00:00", "2026-10-10T00:00:00+00:00"])
    monkeypatch.setattr("paxveil.core.sources.utcnow", lambda: next(times))
    cache = SnapshotCache(tmp_path)
    first = await cache.put("request", "OSV", {"results": [{}]}, 3600)
    second = await cache.put("request", "OSV", {"results": [{}]}, 3600)
    value = await cache.get("request")
    assert first["snapshot_hash"] == second["snapshot_hash"]
    assert value["fetched_at"] == "2026-10-10T00:00:00+00:00"
    with sqlite3.connect(cache.path) as db:
        row = db.execute("SELECT fetched_at,count(*) FROM snapshots").fetchone()
    assert row == ("2026-10-09T00:00:00+00:00", 1)


@pytest.mark.asyncio
async def test_legacy_snapshot_cache_migrates_without_losing_payload(tmp_path):
    fetched = datetime.now(UTC).isoformat()
    with sqlite3.connect(tmp_path / "sources.sqlite3") as db:
        db.executescript(
            "CREATE TABLE snapshots(hash TEXT PRIMARY KEY,source TEXT,fetched_at TEXT,body TEXT); CREATE TABLE cache(key TEXT PRIMARY KEY,snapshot_hash TEXT,expires_at REAL);"
        )
        db.execute(
            "INSERT INTO snapshots VALUES (?,?,?,?)",
            ("digest", "OSV", fetched, '{"results":[]}'),
        )
        db.execute("INSERT INTO cache VALUES (?,?,?)", ("request", "digest", 0))
    cache = SnapshotCache(tmp_path)
    value = await cache.get("request")
    assert value["data"] == {"results": []}
    assert value["fetched_at"] == fetched


@pytest.mark.asyncio
async def test_payload_budget_evicts_oldest_entry_in_utf8_bytes(tmp_path, monkeypatch):
    instant = [1000000.0]
    monkeypatch.setattr("paxveil.core.sources.time.time", lambda: instant[0])
    cache = SnapshotCache(tmp_path, max_bytes=100)
    await cache.put("old", "PyPI", {"value": "я" * 30}, 3600)
    instant[0] += 1
    await cache.put("new", "PyPI", {"value": "ы" * 30}, 3600)
    assert await cache.get("old") is None
    assert (await cache.get("new"))["data"] == {"value": "ы" * 30}
    with sqlite3.connect(cache.path) as db:
        assert db.execute("SELECT SUM(length(CAST(body AS BLOB))) FROM snapshots").fetchone()[0] <= 100
        assert db.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_key_budget_and_shared_snapshot_references(tmp_path, monkeypatch):
    instant = [1000000.0]
    monkeypatch.setattr("paxveil.core.sources.time.time", lambda: instant[0])
    cache = SnapshotCache(tmp_path, max_bytes=1000, max_keys=2)
    for key in ("first", "second", "third"):
        await cache.put(key, "OSV", {"value": 1}, 3600)
        instant[0] += 1
    assert await cache.get("first") is None
    assert (await cache.get("second"))["data"] == {"value": 1}
    assert (await cache.get("third"))["data"] == {"value": 1}
    with sqlite3.connect(cache.path) as db:
        assert db.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 1
    await cache.put("second", "OSV", {"value": 2}, 3600)
    with sqlite3.connect(cache.path) as db:
        assert db.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 2
    await cache.put("third", "OSV", {"value": 2}, 3600)
    with sqlite3.connect(cache.path) as db:
        assert db.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_stale_metadata_retained_for_seven_days_without_freshness_claim(tmp_path, monkeypatch):
    instant = [1000000.0]
    monkeypatch.setattr("paxveil.core.sources.time.time", lambda: instant[0])
    cache = SnapshotCache(tmp_path)
    await cache.put("old", "OSV", {"value": 1}, 1)
    instant[0] += 2
    assert (await cache.get("old"))["fresh"] is False
    instant[0] += 7 * 86400
    assert await cache.get("old") is None
    await cache.put("current", "OSV", {"value": 2}, 3600)
    with sqlite3.connect(cache.path) as db:
        assert db.execute("SELECT key FROM cache").fetchall() == [("current",)]
        assert db.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_oversized_replacement_does_not_keep_previous_fresh_payload(tmp_path):
    cache = SnapshotCache(tmp_path, max_bytes=30)
    await cache.put("request", "OSV", {"value": 1}, 3600)
    metadata = await cache.put("request", "OSV", {"value": "x" * 100}, 3600)
    assert metadata["snapshot_hash"] and await cache.get("request") is None
    with sqlite3.connect(cache.path) as db:
        assert db.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 0


@pytest.mark.parametrize("limits", [{"max_bytes": 0}, {"max_bytes": -1}, {"max_keys": 0}])
def test_cache_limits_must_be_positive(tmp_path, limits):
    with pytest.raises(ValueError, match="positive"):
        SnapshotCache(tmp_path, **limits)


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_replaced_large_payload_reclaims_physical_space(tmp_path, legacy):
    if legacy:
        with sqlite3.connect(tmp_path / "sources.sqlite3") as db:
            db.executescript(
                "CREATE TABLE snapshots(hash TEXT PRIMARY KEY,source TEXT,fetched_at TEXT,body TEXT); CREATE TABLE cache(key TEXT PRIMARY KEY,snapshot_hash TEXT,expires_at REAL);"
            )
    cache = SnapshotCache(tmp_path, max_bytes=4 * 1024 * 1024)
    await cache.put("request", "PyPI", {"value": "x" * (3 * 1024 * 1024)}, 3600)
    before = cache.path.stat().st_size
    await cache.put("request", "PyPI", {"value": "small"}, 3600)
    assert cache.path.stat().st_size < before / 2
    assert (await cache.get("request"))["data"] == {"value": "small"}
    with sqlite3.connect(cache.path) as db:
        assert db.execute("PRAGMA auto_vacuum").fetchone()[0] == 2


def test_concurrent_writes_cannot_exceed_global_cache_limits(tmp_path):
    cache = SnapshotCache(tmp_path, max_bytes=512, max_keys=7)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda index: cache._put(str(index), "OSV", {"value": str(index) * 25}, 3600), range(40)))
    with sqlite3.connect(cache.path) as db:
        assert db.execute("SELECT count(*) FROM cache").fetchone()[0] <= 7
        assert db.execute("SELECT COALESCE(SUM(length(CAST(body AS BLOB))),0) FROM snapshots").fetchone()[0] <= 512
        assert (
            db.execute(
                "SELECT count(*) FROM snapshots WHERE NOT EXISTS (SELECT 1 FROM cache WHERE cache.snapshot_hash=snapshots.hash)"
            ).fetchone()[0]
            == 0
        )


@pytest.mark.asyncio
async def test_durable_cache_reuses_snapshot_and_refreshes(tmp_path):
    hits = []

    def handle(request):
        hits.append(request.url)
        return httpx.Response(200, json={"info": {"version": "1"}})

    cache = SnapshotCache(tmp_path)
    async with Sources(cache=cache, transport=httpx.MockTransport(handle)) as sources:
        await sources.release("safe-name", "1")
        await sources.release("safe-name", "1")
        assert len(hits) == 1
        assert sources.records[-1]["status"] == "cached"
    async with Sources(
        cache=SnapshotCache(tmp_path),
        refresh=True,
        transport=httpx.MockTransport(handle),
    ) as sources:
        await sources.release("safe-name", "1")
        assert len(hits) == 2
        assert sources.records[-1]["snapshot_hash"]


@pytest.mark.asyncio
async def test_osv_batch_pagination_preserves_correspondence(tmp_path):
    def handle(request):
        queries = json.loads(request.content)["queries"]
        if len(queries) == 2:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"vulns": [{"id": "GHSA-a"}], "next_page_token": "next"},
                        {},
                    ]
                },
            )
        assert queries[0]["page_token"] == "next"
        return httpx.Response(200, json={"results": [{"vulns": [{"id": "GHSA-b"}]}]})

    async with Sources(cache=SnapshotCache(tmp_path), transport=httpx.MockTransport(handle)) as sources:
        result = await sources.osv_batch([{"name": "a", "version": "1"}, {"name": "b", "version": "2"}])
        assert result == {("a", "1"): ["GHSA-a", "GHSA-b"], ("b", "2"): []}


@pytest.mark.asyncio
async def test_source_allowlist_blocks_ssrf_and_redirect(tmp_path):
    async with Sources(
        cache=SnapshotCache(tmp_path),
        transport=httpx.MockTransport(lambda _: httpx.Response(302, headers={"location": "http://127.0.0.1"})),
    ) as sources:
        for url in [
            "http://pypi.org/",
            "https://127.0.0.1/",
            "https://pypi.org:8443/",
            "https://password@pypi.org/",
        ]:
            with pytest.raises(SourceError):
                await sources.request("PyPI", "GET", url)
        with pytest.raises(SourceError):
            await sources.release("a", "1")


@pytest.mark.asyncio
async def test_no_stale_fallback_on_failed_refresh(tmp_path):
    cache = SnapshotCache(tmp_path)
    async with Sources(
        cache=cache,
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"good": True})),
    ) as sources:
        await sources.release("a", "1")
    async with Sources(
        cache=cache,
        refresh=True,
        transport=httpx.MockTransport(lambda _: httpx.Response(404)),
    ) as sources:
        with pytest.raises(SourceError):
            await sources.release("a", "1")
        assert sources.records[-1]["status"] == "not_found"


@pytest.mark.asyncio
async def test_malformed_osv_batch_never_becomes_a_clean_query(tmp_path):
    async with Sources(
        cache=SnapshotCache(tmp_path),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"results": [None]})),
    ) as sources:
        with pytest.raises(SourceError):
            await sources.osv_batch([{"name": "a", "version": "1"}])


@pytest.mark.asyncio
async def test_invalid_epss_probability_is_unknown(tmp_path):
    async with Sources(
        cache=SnapshotCache(tmp_path),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"data": [{"cve": "CVE-2024-12345", "epss": "4.0"}]})
        ),
    ) as sources:
        with pytest.raises(SourceError):
            await sources.epss(["CVE-2024-12345"])
