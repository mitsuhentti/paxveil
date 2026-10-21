# Public source cache

The cache stores public JSON responses from OSV, PyPI, deps.dev, FIRST EPSS and CISA KEV. It contains no uploaded manifest, account profile or Telegram token. Account reports keep their own source provenance in PostgreSQL; the cache is an optional reusable copy of public metadata.

| Setting | Default | Meaning |
| --- | --- | --- |
| `PAXVEIL_CACHE_DIR` | `runtime/cache` | Directory containing `sources.sqlite3` |
| `PAXVEIL_CACHE_MAX_BYTES` | 268,435,456 bytes (256 MiB) | Sum of distinct cached JSON payloads in UTF-8 bytes |
| `PAXVEIL_CACHE_MAX_KEYS` | 10,000 | Maximum retained request keys |

Both limits must be positive. They apply to the shared SQLite cache directory across processes. Each write and its eviction run in one `BEGIN IMMEDIATE` transaction. Startup also applies the configured limits, so reducing a limit takes effect when a source client next opens the cache.

Request keys hash the HTTP method, allowlisted URL and request body. A response is serialized consistently and identified by its SHA-256 digest. Identical payloads share one immutable snapshot. Each request key keeps its own fetch time and expiry, so refetching unchanged data updates freshness without rewriting the original snapshot's timestamp.

Expired responses are not silently substituted for current source data. A successful response is reused only within that source's TTL. Unreferenced snapshots are removed, and request keys older than seven days are removed on the next cache write or startup. Older keys are also excluded from reads before that cleanup occurs. When a key or payload limit is reached, the oldest retained request keys are evicted. A response larger than the entire payload budget can still be analyzed; its body is not cached, and any previous value for the same request key is removed.

The byte setting bounds retained JSON payloads, not total filesystem usage. SQLite pages, indexes and temporary WAL/journal files need additional space. New caches use incremental vacuum. Legacy caches are converted after enough free space accumulates. Best-effort compaction runs only after at least 1 MiB and 25% of database pages are free; incremental maintenance reclaims at most 2,048 pages per pass and retries later when another process holds a lock. Keep free disk space beyond the payload budget and include the cache directory in disk monitoring.

## Verification

`backend/tests/test_core_sources.py` covers legacy schema migration, immutable payload identity and fetch timestamps, UTF-8 byte accounting, shared references, key eviction, seven-day cleanup, oversized replacements, space reclamation for new and legacy databases, and concurrent writes from eight threads. It also checks source allowlisting, disabled redirect following, pagination and unavailable-source behavior. Source/service/resource tests passed together on 21 October 2026: 47 tests, with one upstream Starlette/httpx deprecation warning. They use isolated temporary data and controlled source responses.

The cache uses SQLite independently of PostgreSQL. `scripts/database-ops.py verify-concurrency` separately checks PostgreSQL queue claims, fencing, account deletion, shared catalog upserts and a request counter under concurrent connections in a disposable database. Its evidence must be regenerated after changes; source unit tests alone do not establish that the PostgreSQL check has passed.
