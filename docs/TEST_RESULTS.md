# Verification results

Latest full run: **21 October 2026**, Windows, project Python 3.11 environment. Evidence below is limited to the checks executed. Historical observations retain their dates.

## Current automated and PostgreSQL checks

| Check | Observed result |
| --- | --- |
| Full backend suite | **178 passed, 2 skipped, 1 warning in 46.75 seconds** |
| TypeScript checking | Passed |
| Production frontend build | Passed |
| Source/service/public-resource subset | 47 passed, 1 existing warning in 12.40 seconds |
| Database operations script | Ruff and Python compilation passed |
| Real PostgreSQL concurrency | Passed in a disposable database; working database unchanged |
| Native supervisor checker | **19/19 passed** after the guard fix |

The backend invocation, from `backend`, is:

```powershell
python -m pytest -q -m "not integration" -rs
```

The two skips are deliberate opt-in public-source checks: `test_real_osv_pypi_and_cve_match` and `test_real_package_with_no_known_osv_matches`. They require `PAXVEIL_LIVE_TESTS=1` and were not enabled for this suite. Live official-source evidence is recorded separately in [CORE_VALIDATION.json](CORE_VALIDATION.json) and [LIVE_ACCEPTANCE.json](LIVE_ACCEPTANCE.json).

The warning is `StarletteDeprecationWarning` concerning the FastAPI/Starlette test client's httpx adapter. It did not fail the suite. The pinned adapter remains a dependency compatibility boundary.

The current real PostgreSQL run checked:

- Eight threads and 24 requests to enqueue one project scan, producing one job.
- 24 pending jobs, 40 claim attempts and 24 distinct claim tokens.
- Expired-lease recovery and rejection of a stale worker's result.
- Account deletion during claim, successful analysis and failed analysis.
- Concurrent shared package/version/advisory ingestion with opposite input ordering.
- A database request counter shared by independent connections: exactly 11 accepted out of 64 attempts, no counter growth after rejection and recovery at the next fixed window.

The verification migrated a disposable database, performed no source requests and removed that database afterward. The working database was not changed. [POSTGRES_CONCURRENCY_VALIDATION.json](POSTGRES_CONCURRENCY_VALIDATION.json) is the sanitized result.

## Coverage

The suite covers parsing, environment markers, uncertainty, official-source response validation, allowlists, immutable cache snapshots, byte/key bounds, eviction, legacy migration, physical reclamation and concurrent cache writes. It checks aliases, affected ranges, priority factors and restrictions on metadata resolution.

API/resource coverage includes authentication, cookies, owner isolation, streamed upload limits, one-use linking, safe merges, active-job deduplication, account budgets, rolling job windows, persistent settings, export privacy, deletion cascades, bounded sessions/history and maintenance rotation.

Bot tests use actual aiogram dispatch with controlled transports. Component checks connect synthetic updates to real FastAPI routes, isolated SQLite storage and the durable worker with controlled analysis data. Notification/worker cases include quiet hours and DST, digests, category/threshold changes, unsubscribe, retries, lease recovery, claim fencing, incomplete-source suppression and baseline recovery.

Fixture reports and advisory names are confined to tests. SQLite cases alone do not establish PostgreSQL locking; that boundary is covered by the separate real PostgreSQL run above.

## Dated operational and live evidence

| Date | Executed observation | Evidence |
| --- | --- | --- |
| 11–12 October | Live official-source scan and FixLab proposals; five pinned dependencies, 12 deduplicated findings, zero known OSV findings for resolved Balanced/Maximum proposals | [CORE_VALIDATION.json](CORE_VALIDATION.json) |
| 11–12 October | Live API upload, persistence, CVE check, Watch settings and foreign-owner rejection | [LIVE_ACCEPTANCE.json](LIVE_ACCEPTANCE.json) |
| 21 October | Fresh private backup restored into a separate database; 20 tables/251 rows; 87,355 bytes; all fingerprints matched | [BACKUP_VALIDATION.json](BACKUP_VALIDATION.json) |
| 21 October | API/web HTTP 200, exact process identities, sign-in startup/supervisor and daily backup checkpoint; selected runtime data, logs, private backups and secret file EFS-encrypted | [CURRENT_RUNTIME_VALIDATION.json](CURRENT_RUNTIME_VALIDATION.json) |
| 21 October, 13:54:43 UTC | Telegram getMe passed, all 12 default/Russian commands matched, no webhook; earlier connection failure recovered | [PUBLIC_LAUNCH_VALIDATION.json](PUBLIC_LAUNCH_VALIDATION.json) |
| Earlier browser runs | Working UI/API scenarios, desktop/mobile and light/dark screenshots | [FRONTEND_VALIDATION.md](FRONTEND_VALIDATION.md), [DESIGN_REVIEW.md](DESIGN_REVIEW.md) |

A normal stop/start of the existing runtime completed on 21 October, followed by a fresh 19/19 supervisor check: [NATIVE_SUPERVISOR_VALIDATION.json](NATIVE_SUPERVISOR_VALIDATION.json). Earlier performance/memory snapshots are local bounded observations, not capacity measurements.

## Browser acceptance, 21 October

Real browser interaction with the running application covered registration of a QA owner, explicit sample selection, cancellation clearing the selected file, and a genuine requests 2.31.0 scan. That scan finished in about four seconds with three findings and five displayed source entries.

The closed-findings filter returned zero rows and reset restored the result list. A running FixLab task survived navigation and reload. Balanced and Maximum Coverage proposed requests 2.34.2 with zero known findings for the proposal; Minimal Change reported insufficient data. A historical scan permalink survived reload and returned to the latest report; history labels were readable.

Settings exposed unsaved changes and saved successfully, including the Windows upload environment. Owner-specific sessionStorage drafts survived internal navigation. An invalid quiet-hour range displayed an error near the field and focused the missing end time. Mobile content measured 375 pixels without horizontal overflow. The header/save action remained reachable. Escape closed navigation and returned focus; selecting the active route closed the menu, and resizing to desktop removed dialog state and the scroll lock.

[USABILITY_VALIDATION.json](USABILITY_VALIDATION.json) records all 20 checks and five unedited screenshots. These checks do not establish all browser combinations, application compatibility after dependency updates or Telegram-client delivery.

## Human Telegram acceptance

The owner previously confirmed the real `/start` menu, followed by `/privacy`, `/environment` and `/projects`. Today's official Bot API success followed an earlier TelegramNetworkError/TCP failure; it establishes recovery at the recorded time, not continuous availability. Actual client upload/report/FixLab/linking/Watch acceptance remains pending. The new `/example` action invokes real analysis of a public fixture; controlled handler tests are not presented as external Telegram delivery. Continue the [live checklist](TELEGRAM.md#verification-boundary-and-live-acceptance-checklist).

## Unverified boundaries

The complete fresh-machine native bootstrap, public traffic capacity and uptime remain unverified. The [public repository](https://github.com/mitsuhentti/paxveil) and successful [GitHub Actions](https://github.com/mitsuhentti/paxveil/actions/workflows/ci.yml) are available. The selected local deployment can stop with the owner's computer or connection.

FixLab verifies release metadata and known advisories, not application behavior or runtime reachability. Zero known findings is a dated analysis result, not a security guarantee. See [current status](../PROJECT_STATUS.md) and [operations](OPERATIONS_VALIDATION.md).

## Remote CI, 21 October

All three [GitHub Actions jobs](https://github.com/mitsuhentti/paxveil/actions/workflows/ci.yml) passed: backend tests/lint, PostgreSQL migrations and schema checks, queue concurrency and backup restore; frontend typecheck/build; Compose API/worker build/start/readiness and the optional web image build. The workflow runs against each new code commit.
