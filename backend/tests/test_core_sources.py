import json
import sqlite3

import httpx
import pytest

from paxveil.core.sources import SnapshotCache, SourceError, Sources


@pytest.mark.asyncio
async def test_identical_refetch_updates_cache_time_and_preserves_snapshot(
    tmp_path, monkeypatch
):
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
    with sqlite3.connect(tmp_path / "sources.sqlite3") as db:
        db.executescript(
            "CREATE TABLE snapshots(hash TEXT PRIMARY KEY,source TEXT,fetched_at TEXT,body TEXT); CREATE TABLE cache(key TEXT PRIMARY KEY,snapshot_hash TEXT,expires_at REAL);"
        )
        db.execute(
            "INSERT INTO snapshots VALUES (?,?,?,?)",
            ("digest", "OSV", "2026-10-09T00:00:00+00:00", '{"results":[]}'),
        )
        db.execute("INSERT INTO cache VALUES (?,?,?)", ("request", "digest", 0))
    cache = SnapshotCache(tmp_path)
    value = await cache.get("request")
    assert value["data"] == {"results": []}
    assert value["fetched_at"] == "2026-10-09T00:00:00+00:00"


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

    async with Sources(
        cache=SnapshotCache(tmp_path), transport=httpx.MockTransport(handle)
    ) as sources:
        result = await sources.osv_batch(
            [{"name": "a", "version": "1"}, {"name": "b", "version": "2"}]
        )
        assert result == {("a", "1"): ["GHSA-a", "GHSA-b"], ("b", "2"): []}


@pytest.mark.asyncio
async def test_source_allowlist_blocks_ssrf_and_redirect(tmp_path):
    async with Sources(
        cache=SnapshotCache(tmp_path),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(302, headers={"location": "http://127.0.0.1"})
        ),
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
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"good": True})
        ),
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
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"results": [None]})
        ),
    ) as sources:
        with pytest.raises(SourceError):
            await sources.osv_batch([{"name": "a", "version": "1"}])


@pytest.mark.asyncio
async def test_invalid_epss_probability_is_unknown(tmp_path):
    async with Sources(
        cache=SnapshotCache(tmp_path),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"data": [{"cve": "CVE-2024-12345", "epss": "4.0"}]}
            )
        ),
    ) as sources:
        with pytest.raises(SourceError):
            await sources.epss(["CVE-2024-12345"])
