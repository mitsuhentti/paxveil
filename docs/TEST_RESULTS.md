# Automated verification

## Design update, 12 October 2026

The affected Telegram handler/API tests were rerun after copy changes: **24 passed, 1 existing framework warning in 5.17 seconds**. Ruff and formatting of bot presentation passed. Only two assertions were adapted to the new labels; API ownership and callback checks retain their earlier behavior. The frontend production build passed, including TypeScript and page generation. Browser checks through the in-app browser are recorded in [DESIGN_REVIEW.md](DESIGN_REVIEW.md). The full backend results below are the 11 October baseline; this update reran affected coverage.

Executed on **2026-10-11** against the delivered working tree on Windows with the project's Python 3.11 environment. Results are bounded evidence of the tested behavior, not a production certification.

## Final backend checks

From `backend`:

```powershell
python -m pytest -q -m "not integration" -rs
python -m ruff check paxveil tests
```

| Check | Observed result |
| --- | --- |
| Full backend suite | **122 passed, 2 skipped, 1 warning in 32.45 seconds** |
| Notification/worker subset | **33 passed, 1 warning in 15.49 seconds** |
| Streamed multipart security regression | **1 passed, 1 warning in 1.25 seconds** |
| Ruff on backend source and tests | **All checks passed** |
| Suite cases | **124 cases: 122 passed and 2 intentionally skipped** |

Both skips are intentional public-source checks in `tests/test_core_integration.py`: `test_real_osv_pypi_and_cve_match` and `test_real_package_with_no_known_osv_matches`. Their exact condition is `PAXVEIL_LIVE_TESTS != "1"`; the reason is: "Set PAXVEIL_LIVE_TESTS=1 for non-aggressive official public API verification." Those checks remain visible as skips in this invocation because their opt-in guard, rather than the registered `integration` marker, controls execution. This verification did not enable public requests or send Telegram messages. The separate real-source evidence is recorded in `CORE_VALIDATION.json` and `LIVE_ACCEPTANCE.json`.

The one warning is `StarletteDeprecationWarning` from the installed FastAPI/Starlette test client: use of its `httpx` adapter is deprecated. It did not fail a check; the current pinned adapter completed the suite. A future framework migration should review this compatibility boundary.

## Coverage and limits

The suite checks dependency parsing, markers and uncertainty, official-source response validation, source allowlists, durable cache behavior, advisory aliases, affected ranges, priority inputs and metadata resolver restrictions. API checks exercise authentication, cookies, owner isolation, upload validation, account-link expiry and rotation, owner-safe merges, persistent settings, active-job deduplication, deletion cascades and Fire Drill's retained inventory during interrupted rescans.

The streamed-upload regression sends an authenticated multipart request through the actual FastAPI ASGI application with an asynchronous byte generator and no Content-Length. The file is small and valid; two ignored padding fields each remain below the multipart parser's per-part limit. Once the cumulative body exceeds 1 MiB plus 16 KiB of multipart allowance, the API returns HTTP 413, stops consuming the stream before its end and creates no project. This verifies the cumulative receive guard rather than obtaining a rejection from the separate file-size or multipart-part limit. The isolated test makes no external source or Telegram request.

Bot tests use actual aiogram dispatch with controlled Telegram/HTTP transports. A separate component test sends synthetic updates through the real FastAPI ASGI routes, an isolated temporary SQLite database and the durable worker. Notification/worker checks include quiet hours and DST, digests, threshold/category changes, unsubscribe, retry limits, recovery of expired leases, claim-token fencing of stale successes/failures/deliveries, baseline recovery after OSV failure, incomplete-lookup suppression and CVE-alias deduplication.

Artificial reports and advisory identities are confined to test fixtures. API/worker database tests use temporary SQLite databases, so passing them does not establish PostgreSQL locking behavior under concurrent real processes. These tests also do not establish external Telegram delivery, public hosting, Docker startup, package behavioral compatibility or the standalone browser runner's execution. Consult `FRONTEND_VALIDATION.md`, `TELEGRAM.md`, `REVIEW.md` and the live acceptance evidence for those separate boundaries.

## Deterministic clock correction

The final verification found a test-fixture defect after the calendar date advanced: notification tests froze the worker clock at 2026-10-10, while their newly created jobs inherited the real 2026-10-11 ORM default for `run_at`. Four tests then failed because those jobs were correctly not yet due according to the frozen worker clock. The shared fixture helper now accepts an explicit `run_at`, and the outbox fixture supplies its frozen instant. No production source change was needed for this correction; all four affected behaviors passed in the final suite.

## Separate executed operational checks

The implementation owner subsequently completed initialization of the prepared runtime, native API/web startup and ordinary graceful PostgreSQL stop/start outside the Windows isolation restriction. Genuine bot polling was verified again after that restart. The owner confirmed that `/start` showed the menu in their actual `@PAXVEIL_Bot` client, and bot logs recorded two handled updates before the final restart. These observations are separate from the 122 automated tests above; see [OPERATIONS_VALIDATION.md](OPERATIONS_VALIDATION.md) for the runtime evidence.

Human Telegram file uploads, account linking, reports and Watch delivery remain to be accepted through the [live checklist](TELEGRAM.md#verification-boundary-and-live-acceptance-checklist). Docker execution, a fresh-machine bootstrap, backup restoration and PostgreSQL concurrency fault injection remain unverified.
