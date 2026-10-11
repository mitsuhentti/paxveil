# Independent backend review

Scope: API ownership checks, authentication and Telegram linking, PostgreSQL job leases, scan ingestion, notification scheduling and delivery. Reviewed after successful local smoke tests on 2026-10-10 and inspected the final remediation on 2026-10-11. This is a bounded code review, not a penetration test or a certification.

## Remediation verification

A final code inspection confirmed User-row serialization for linking with a consistent User→LinkCode lock order, locked/token-checked job failure updates, delivery claim tokens with locked finalization, and Fire Drill's latest completed/partial non-null inventory selection. The core exposes a separately tested `vulnerability_lookup_complete` flag; HTTP success alone cannot establish a usable baseline. Priority changes are suppressed when CVSS, EPSS or KEV availability differs in either direction, and KEV unknown-to-known restoration no longer emits a newly exploited event. `UploadLimitMiddleware` counts raw ASGI receive bytes before multipart parsing, including requests without a declared Content-Length, while the endpoint retains its separate file-size bound. The final backend suite passed 122 tests; controlled temporary-SQLite tests cover stale worker results/failures and stale notification finalization. A real-ASGI streamed multipart regression confirms HTTP 413 without Content-Length, early consumption termination and no project persistence; its valid small file and individually bounded padding fields avoid masking a missing body guard with other upload limits. PostgreSQL process-pause races were not fault-injected. Dedicated enrichment-restoration test cases were not included in that suite; the availability-suppression remediation statement is based on code inspection. The findings below retain their original triggers for traceability.

## Confirmed implementation strengths

Project, scan, job, history, notification and finding-state API reads constrain access to the authenticated owner. IDs are UUIDs, but access control relies on owner predicates rather than ID secrecy. Passwords use per-user salts and PBKDF2-SHA256 with 600,000 iterations. Session and one-use linking tokens are stored as SHA-256 hashes. Browser cookies are HttpOnly and SameSite=Lax; production must enable Secure cookies. Bot identity/link endpoints require a separate key and reject an empty configured key. Telegram account merges reject a previous account that already has a web password.

Scan and FixLab enqueue paths serialize through a project row lock and deduplicate outstanding jobs. PostgreSQL claims use `FOR UPDATE SKIP LOCKED`, commit a lease and a claim token, then release locks during external work. The successful completion path locks the job and checks the token before committing. Job execution timeout is ten minutes and the claim lease is fifteen minutes. Report ingestion and job completion are committed together. This establishes useful transactional boundaries for recovery.

Uploaded content is not executed. Official source destinations are allowlisted, HTTP redirects are disabled, and FixLab uses binary metadata behind a dedicated PyPI-only proxy. Known vulnerabilities, runtime reachability, CVSS impact and EPSS probability remain distinct. Controlled test advisories are separate from real-source validation reports.

## Findings sent to the implementation owner

### P1: Telegram target account is not serialized during linking

At review time `api.link_code` deleted earlier codes and added a new one without locking the User row or enforcing a unique `user_id` on LinkCode. Two simultaneous requests can therefore issue two codes for one account. `api.bot_link` locked the selected code and the previous Telegram user but obtained the target User through `db.get`, without a row lock. Two distinct code consumptions can both observe an empty target Telegram ID, overwrite it, and issue sessions for the same web account to two Telegram IDs.

This follows from the transaction boundaries and schema; a concurrent live account-link attempt was not performed. Serialize code replacement and target-account consumption on the same User row. Use a consistent lock order to avoid a User/LinkCode deadlock. Re-check account ownership and Telegram ID after acquiring the locks.

### P1: Fire Drill discards the last known inventory while a rescan is queued

At review time `/api/fire` selected the latest Scan regardless of whether it had a report. A newly queued or running rescan therefore replaced an earlier completed inventory with `{}`. If the CVE advisory is retrievable, the core can see no dependencies and return `no_match`, although the previous saved inventory matched that CVE.

This is verified by the API's selection logic and the core's documented input handling; the review did not modify live projects. Use the latest non-null report, identify its age, and distinguish projects with no analyzed inventory as insufficient data. A project with missing inventory must not be treated as checked and unaffected.

### P2: Job exception handling lacks atomic claim fencing

The success path uses `SELECT ... FOR UPDATE`, checks `running` status and compares the claim token. At review time the exception path used `db.get(Job)` and compared the token without a row lock or a running-status predicate. It can read the old token, race lease recovery/new claiming, then commit status, error, next-run time and lease changes over the successor's claim.

This is a code-inspection finding; the paused-process race was not executed against the live database. Mirror the successful-completion lock/check in the failure handler, or make the failure update conditional on both claim token and status in one SQL statement. Leave the successor untouched when the conditional update affects zero rows.

### P2: Notification attempts have no claim token

Notification delivery claims a two-minute lease but stores no delivery claim token. Its completion path checks only that status is `sending`. A sender paused past lease expiry can finish after another worker has reclaimed the notification and modify the newer attempt's state. The twenty-second HTTP timeout makes this uncommon during normal execution, but a process pause is outside that timeout guarantee.

Add a claim token or monotonically increasing attempt generation and fence finalization atomically. Telegram's send API does not supply an application idempotency key, so a crash after remote acknowledgement and before the local commit can still produce duplicate external delivery. Document at-least-once delivery explicitly; database event deduplication alone does not establish exactly-once Telegram messages.

### P2: Partial enrichment creates misleading Watch changes

A controlled in-memory probe of `notifications.event_changes` showed:

1. Same advisory with KEV `true`, priority 65 → KEV `null`, priority 40 emitted a priority event.
2. KEV `null`, priority 40 → KEV `true`, priority 65 emitted both priority and exploitation events.

The advisory did not change in the probe; only source availability did. Missing EPSS/KEV must not be presented as a substantive risk decrease or newly observed exploitation. Compare evidence with compatible availability, preserve the latest known enrichment baseline, or suppress availability-only priority events. A `null` → `true` KEV transition needs an explicit unknown-to-known description or comparison with the last known KEV value.

At review time the baseline chooser also accepted reports without any source records; the implementation owner was already correcting that behavior. An HTTP source record marked `ok` is insufficient by itself: OSV shape validation can fail after a successful HTTP response has been recorded. Expose and use an explicit vulnerability-lookup completeness field, while allowing legitimate findings from successful subqueries to remain visible.

### P2: Content-Length rejection is not a streaming body limit

The middleware rejects excessive declared Content-Length and the endpoint reads at most the file limit plus one byte. A multipart request without Content-Length, or one that misstates it, can still be parsed and spooled by Starlette before the endpoint's bounded file read. This leaves disk and parser resource consumption outside the intended 1 MiB boundary.

This finding is based on the middleware/dependency ordering; no large-body test was sent to the running service. Bound ASGI receive bytes or use a deployment proxy with a hard request-body limit, and maintain the application limit as defense in depth.

## Production boundaries and untested conditions

- Shared Package/PackageVersion/Advisory ingestion uses read-then-insert. Concurrent workers analyzing different projects can collide on unique keys. Transactions roll back and retry, so this is primarily a recovery/throughput concern; use PostgreSQL upserts when adding multiple workers.
- Limits are process-local and account storage/project quotas are absent. A public multi-instance deployment requires shared rate limits and resource quotas.
- On 2026-10-11 the owner's locally configured bot passed the official `getMe` check and polling started successfully for `@PAXVEIL_Bot`. The owner confirmed that `/start` displayed the menu in their actual Telegram client, and logs recorded two handled updates. Polling was verified again after the native restart. Human file/report/link acceptance and actual Watch delivery remain pending. Post-send crashes were not fault-tested through the real Telegram network; quiet hours, filtering and handler behavior use controlled test inputs.
- PostgreSQL concurrent linking, lease-expiry pauses and notification reclaim races were reviewed statically, not fault-injected in the running service. Controlled temporary-SQLite tests exercise claim-token fencing but do not establish PostgreSQL lock behavior.
- Source snapshot retention, session cleanup, backup/restore and privacy policies require deployment-specific configuration and operational verification.
- SQLite is suitable for bounded local tests; PostgreSQL is the supported durable concurrent-worker deployment.

## Measured source-cache observation

`CORE_VALIDATION.json` records a fresh public-source scan of five pinned PyPI dependencies with twelve deduplicated findings: **42.047 seconds**. It was partial because an independent deps.dev cross-check timed out; OSV, PyPI, FIRST EPSS and CISA returned data. The subsequent cached scan returned the same five dependencies and twelve findings in **0.062 seconds**, with recorded-version coverage complete. These are measured end-to-end observations with differing source availability, not an isolated latency benchmark or a promised speedup.

The same evidence file records real FixLab resolutions followed by actual OSV scans with zero known findings for Balanced and Maximum Coverage. Minimal Change had no eligible proposal. The initial thirty-six core unit tests passed in 1.42 seconds, and two opt-in official-source checks passed in 1.17 seconds. Following this review's validation/completeness and cache-timestamp fixes, **41 core unit tests passed in 2.17 seconds**. Results are time-specific and do not establish application behavioral compatibility.

## Source credential and packaging check

On 2026-10-11, a final pass inspected 114 tracked/untracked text artifacts (875,167 bytes), including the README/deployment/status documents and excluding local `.env`, runtime/cache files, dependency directories and build output. Pattern checks found no operational Telegram, GitHub, AWS or other API credentials or private-key blocks. The sole Telegram-shaped candidate was the explicitly named `SYNTHETIC_TOKEN` in the isolated bot test harness. A separate literal-assignment scan found no operational-secret candidates. The local `.env` was confirmed untracked and Git-ignored; `.env.example` contains blank values or replacement placeholders. This bounded pattern inspection does not cover Git history or image pixels and is not proof against every possible secret format.

Compose parsed successfully with the available YAML library, including its backend anchor, six services, migration/health dependencies and loopback-only published API/web ports. PowerShell parsing found no syntax errors in `init.ps1`, `start.ps1` or `stop.ps1`. Final script inspection confirmed startup refuses occupied local ports before mutations, verifies the expected project-owned postmaster PID before migrations, and waits for API/web HTTP readiness. Stop verifies the recorded UTC start time before killing the corresponding process tree or asking `pg_ctl` to stop the project cluster. PowerShell 7 is required and documented; script operational execution is recorded separately by the implementation owner. Docker/Compose was unavailable, so container startup was not executed.

Final `init.ps1` inspection confirmed its optional `RuntimeDirectory` selects an explicit project runtime while preserving an existing `.env`. When an older native configuration lacks `POSTGRES_PASSWORD`, the script appends that setting from the existing local database URL; it does not replace the database password, Telegram token or bot service key. All three scripts declare `#requires -Version 7.0`. The implementation owner completed initialization of the prepared runtime and an ordinary graceful PostgreSQL shutdown/start outside the Windows isolation restriction. See [OPERATIONS_VALIDATION.md](OPERATIONS_VALIDATION.md) for that executed operational evidence; this does not establish a fresh-machine bootstrap, backup recovery or PostgreSQL concurrency fault testing.
