# Public bot limits and data lifecycle

The default limits are suitable for the first public launch on one machine. They are enforced by PostgreSQL transactions rather than by one API process's memory. Operators can raise the documented environment settings after measuring capacity.

| Limit | Default | Configuration |
| --- | --- | --- |
| Projects per account | 10 | `MAX_PROJECTS_PER_USER` |
| Active scan/FixLab jobs per account | 3 | `MAX_ACTIVE_JOBS_PER_USER` |
| New scan/FixLab jobs in the preceding hour | 10 | `MAX_ANALYSIS_JOBS_PER_HOUR` |
| Stored manifests and report payloads per account | 64 MiB | `MAX_OWNER_STORAGE_BYTES` |
| One completed report | 8 MiB | `MAX_REPORT_BYTES` |
| Active sessions per account | 20 | `MAX_SESSIONS_PER_USER` |
| Finished scans retained per project | 30, plus the last complete OSV baseline if older | `RETAINED_SCANS_PER_PROJECT` |
| Finding status transitions retained per project | Latest 1,000 across all findings | `RETAINED_STATUS_CHANGES_PER_PROJECT` |
| Completed/failed jobs retained | 30 days | `TERMINAL_JOB_RETENTION_DAYS` |
| Notifications and delivery logs retained | 90 days | `NOTIFICATION_RETENTION_DAYS` |
| API requests | 240 per account/IP per minute | Fixed request window |
| Web authentication requests | 30 per IP per minute | Fixed request window |
| CVE checks | 10 per account per hour | Fixed request window |
| Account exports | 3 per account per hour, at most 40 MiB each | Fixed request window |

The job limit uses a rolling hour. Request, CVE and export limits use fixed UTC time windows and return `Retry-After`. Request counters store a SHA-256 digest of the identity, route class and window; they contain no raw IP address or session token. A PostgreSQL upsert atomically increments each counter. A rejected request does not keep increasing it.

Account row locks serialize project creation and job budgets across API processes and the Watch scheduler. An already pending scan/FixLab request returns the same job and consumes no additional analysis allowance. Watch uses the same budget; a blocked scheduled check is deferred to the next Watch interval. Uploads remain limited to 1 MiB and 300 dependencies. The service never executes an uploaded program or installs its packages.

The storage budget counts manifests, scan reports, job results, FixLab scenario copies, source provenance, notification payloads, finding states and their status history. Finding states and history are counted as compact JSON containing persisted fields, with timestamps in ISO format. The calculation streams those rows rather than loading the entire history. It is a payload quota, not an estimate of PostgreSQL's physical disk space. Global public package/advisory reference rows and database indexes are outside this per-account quota. A report that exceeds the report or account budget fails with an actionable message and is not retried automatically. The previous saved reports remain available.

The separate public source cache has a shared 256 MiB payload budget and 10,000 request-key limit. Its lifecycle and configuration are documented in [PUBLIC_CACHE.md](PUBLIC_CACHE.md).

The worker checks retention every five minutes, between jobs. Each maintenance transaction processes at most 100 owners, skipping owner rows already locked by another process. It rotates by the last maintenance timestamp so subsequent batches reach other accounts. A long-running analysis can delay this interval. Expired sessions, one-use Telegram link codes and request windows are removed. Each actual finding status transition also trims that project's history to the latest 1,000 entries under the account lock; maintenance applies the same cap to older existing records. Timestamp ties use the increasing history ID. Trimming history preserves the finding's current status. Removing old scans also removes their normalized dependencies, findings, provenance snapshots, linked jobs and FixLab scenarios through database cascades. Running work and the latest complete OSV comparison are preserved. Old unsent notifications expire after 90 days; a notification currently leased for delivery is preserved until delivery/recovery finishes.

## Account controls

`GET /api/account/export` requires an owner's session. It exports that account's settings, UTF-8 manifests, scans, finding status history, subscriptions, jobs and notifications. Scan reports are included once. Password hashes, session tokens, Telegram link codes, service credentials and other owners' records are excluded. The response is JSON. Exports above 40 MiB return a clear error rather than silently omitting records; individual project reports can be saved before deleting unwanted projects and repeating the export.

`DELETE /api/account` requires the owner's session and the JSON body `{"confirmation":"DELETE"}`. The bot adds an owner-bound, expiring confirmation button before making this request. The database deletes the user and cascades projects, reports, jobs, subscriptions, sessions, link codes, notifications and delivery logs. The endpoint clears the browser session cookie. A later `/start` creates a new empty Telegram account.

Deletion affects the active database. Existing operator backups can contain older records until their stated backup retention expires. The operator must protect those backups and disclose that retention in the public privacy policy.

The bot's selected Python version/platform are account defaults in `upload_python_version` and `upload_platform`. They apply to new uploads. Existing projects keep the environment stored when they were created.

## Validation

`backend/tests/test_public_resources.py` checks an atomic counter across concurrent database connections, owner-specific limits, rolling-hour recovery, rejected upload rollback, private exports, account cascades, session bounds, complete-baseline retention, provenance cleanup, maintenance batch rotation, environment validation and permanent resource-limit failures. These controlled tests use isolated SQLite databases; they do not substitute for the separate PostgreSQL concurrency/deployment checks.

`scripts/database-ops.py verify-concurrency` additionally tests the PostgreSQL request counter with 64 attempts from eight concurrent threads, using independent committed connections. It expects exactly 11 accepted requests, a counter that remains capped after rejection and a fresh allowance at the next fixed window. The command creates and removes a disposable database and writes sanitized evidence only after every assertion passes.
