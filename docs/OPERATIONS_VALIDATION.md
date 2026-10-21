# Native runtime verification

Executed on Windows on **11 October 2026** using the project-owned PostgreSQL 18 cluster and Python 3.11 environment in `work/runtime`, outside the source repository. No system component, unrelated database, public service or paid resource was created.

## Preparation and restart

The actual `scripts/init.ps1 -RuntimeDirectory '..\..\work\runtime'` command completed twice against the prepared environment. The backend lock was satisfied; `npm ci` installed 55 packages and reported zero audited vulnerabilities; Next production compilation, strict TypeScript checks and prerendering passed. The initializer retained the configured Telegram token and existing cluster. It added the missing Compose password setting to the ignored local environment by reusing the existing project database password. No secret is included in this evidence.

This verifies re-preparation of the existing environment. The complete bootstrap from an empty checkout, new venv, newly generated environment and new cluster has not been exercised as a single command. Its underlying venv creation, dependency installation and `initdb` operations were separately performed during preparation.

Windows isolation blocked PostgreSQL control signaling and produced autovacuum-worker startup warnings. The explicit development-only `stop.ps1 -ForceDatabase` fallback terminated the verified project process tree. Subsequent startup performed WAL recovery. A SHA-256 comparison of the saved QA project, reports, finding states and subscription row remained unchanged: one scan and three finding states. Contents and credentials were not exported.

Launching the same local services outside that isolation resolved this restriction. After more than one minute of operation, the PostgreSQL log showed no autovacuum-worker startup warning in that run. **Ordinary `stop.ps1`, without `-ForceDatabase`, then completed successfully** with `server stopped` and exit code zero. This is a local control/maintenance observation, not a long-term database reliability benchmark.

The final `start.ps1 -Telegram` run completed with exit code zero. API/database health and the production web page returned HTTP 200. The worker logged its startup; the real bot resumed polling as `@PAXVEIL_Bot`. Alembic found no new upgrade operations. ETL checks returned zero orphan scans, duplicate findings, invalid priorities and completed scans without reports.

The startup guard refuses occupied ports before database mutation, confirms its own PostgreSQL PID and waits for API/web readiness. Shutdown verifies stored PID start times and supports PowerShell 7.5's JSON date conversion. All launch scripts require PowerShell 7.

## Measured evidence

The final [runtime JSON](RUNTIME_VALIDATION.json) records the unchanged QA state after restart and 20 sequential requests per endpoint:

| Endpoint | Median | p95 | Maximum |
|---|---:|---:|---:|
| API/database health | 2.14 ms | 2.56 ms | 6.07 ms |
| Production web HTML | 2.65 ms | 3.42 ms | 6.07 ms |

These lightweight local endpoint samples measure neither scan throughput nor concurrent capacity. The real five-package scan in [CORE_VALIDATION.json](CORE_VALIDATION.json) took 42.047 seconds; a subsequent cached scan took 0.062 seconds. Source availability differed, so the observations do not establish an isolated speedup factor.

[MEMORY_SNAPSHOT.json](MEMORY_SNAPSHOT.json) records one idle observation of readable project-owned process trees: a **646.66 MiB working-set sum** and **457.84 MiB private-commit sum**. Shared pages can be counted more than once, and unreadable/transient children are excluded. These are partial sums rather than total, peak or steady-state application memory.

## Browser and Telegram acceptance

The real production browser retained the QA project and its Investigating finding status after the full restart. Its KEV field correctly distinguished unavailable data. FixLab completed all three strategies through the live API; Balanced and Maximum Coverage proposed Requests 2.34.2 and showed three known findings before, zero in the resolved proposal. Minimal Change reported insufficient data. Fire Drill confirmed CVE-2024-35195 against Requests 2.31.0 and showed official advisory links. See [frontend evidence](FRONTEND_VALIDATION.md) and actual [screenshots](screenshots/).

The owner configured the bot token locally, `getMe` identified the genuine bot, and the owner explicitly confirmed receiving the menu after `/start`. Interactive real-file upload, account linking, report download and Watch delivery still require the owner's Telegram client checklist. Automated synthetic updates remain separate from these live observations. See [TELEGRAM.md](TELEGRAM.md).

Docker/Compose and external CI passed on 21 October; see [GitHub Actions](https://github.com/mitsuhentti/paxveil/actions/workflows/ci.yml). Independent public hosting remains unverified. The final services were left running locally; continuous operation depends on the computer, processes and network remaining available.

## Backup and real PostgreSQL concurrency, 12 October 2026

`scripts/database-ops.py` created a private custom-format dump outside the source repository using an exported read-only snapshot. It then restored into a uniquely named database, compared all public-table row fingerprints against that snapshot and removed the disposable database. All **19 tables and 161 rows** matched in the **74,595-byte** archive. No working database rows or services were changed. [BACKUP_VALIDATION.json](BACKUP_VALIDATION.json) records sanitized counts; the dump and private manifest remain excluded from the delivery.

The helper also migrated a separate disposable PostgreSQL database and exercised real database locking through eight independent-thread sessions. **24 concurrent enqueue requests returned one job**, and **40 claim attempts returned 24 unique claims** from 24 pending jobs. An expired lease was reclaimed with a different token; the stale claim could not overwrite the completed successor. Its analysis report was controlled and made no network source queries. The disposable database was removed. [POSTGRES_CONCURRENCY_VALIDATION.json](POSTGRES_CONCURRENCY_VALIDATION.json) records the scope. This is a locking/fencing observation, not a load-capacity benchmark.

The daily backup helper defaults to seven-day retention and removes only recognized, checksum-valid old backup pairs after a new backup succeeds. It never restores into an existing database. Previous good backups are retained when creation fails. Private off-device backup and hardware-loss recovery have not been demonstrated.

Compose now defaults to a private API/database bot stack, with the browser UI enabled separately. Log rotation, process limits, init processes, read-only backend roots and graceful stop periods are prepared. YAML parsing and backend/helper lint passed locally. The extended CI passed queue concurrency, dump/restore, container readiness and builds on 21 October. [Workflow](https://github.com/mitsuhentti/paxveil/actions/workflows/ci.yml).

## Current observations, 21 October 2026

The dated 11 and 12 October observations above are historical. After the 21 October build and ordinary restart, a fresh read-only [current runtime snapshot](CURRENT_RUNTIME_VALIDATION.json) observed HTTP **200** from both API/database health and production web HTML. PostgreSQL reported revision **b59a10**, with **zero pending, running or retry jobs**. The snapshot also records 23 succeeded jobs and one previously failed terminal job; it does not treat the historical failure as a currently active task.

All five service PIDs and the supervisor PID matched their recorded process start timestamps. The supervision enable flag, matching Windows sign-in entry and daily-backup checkpoint were present. The isolated [supervisor check](NATIVE_SUPERVISOR_VALIDATION.json) passed **19 checks** using the exact current scripts, controlled Python fixture children and a mocked health response. It verified worker recovery, preservation of the other roles, duplicate-supervisor exclusion, stale-manifest recovery, timestamp fencing and fixture cleanup. It did not reboot Windows or exercise an actual Telegram connection.

After the expanded protection helper and ordinary restart completed, Windows EFS attributes were present on every inspected PostgreSQL data file (**1,381**), all four private-backup files, all **18 runtime log files**, all **27 ordinary files directly in the runtime root**, the runtime and rotating-log directories, the local secret file and the encryption operations log. No inspected file in those groups lacked EFS. Counts and encryption booleans are recorded without file contents, user records or credentials. This is an encryption-attribute observation, not a demonstrated recovery of the owner's Windows EFS certificate.

The protection helper covers existing ordinary files directly in the stopped runtime root and traverses the rotating-log directory. It verifies each root target before encryption, refuses linked or external root targets, and encrypts its own operations log last without redirecting into that file. It does not recursively encrypt the Python environment or downloaded executable trees. This closes the earlier gap in protection of existing stdout/error files, rather than relying solely on encrypted-directory inheritance for future files.

The fresh [backup/restore check](BACKUP_VALIDATION.json) matched **20 tables and 251 rows** in an **87,355-byte** custom-format archive. The disposable restore database was removed, and the working database was not mutated by the check. These measurements supersede the older backup counts for the current database while retaining the earlier evidence above.

**The latest read-only Telegram check passed at 13:54 UTC on 21 October.** An earlier official Bot API probe failed with `TelegramNetworkError`, and TCP access to `api.telegram.org:443` failed at 13:49 UTC. After the TCP endpoint became reachable, one permitted retry of the existing read-only validation script identified `@PAXVEIL_Bot`, checked all **12 default and Russian commands**, and confirmed that no webhook was configured. The fresh [public launch evidence](PUBLIC_LAUNCH_VALIDATION.json) records the successful official Bot API calls. No Telegram messages were sent and no user updates were consumed. The earlier failure and later recovery remain point-in-time observations; they do not establish continuous availability or a fresh human-client upload/report acceptance check.

The owner-computer deployment remains dependent on power, Windows sign-in and network access. The successful dated browser and human Telegram observations remain useful evidence of those specific sessions, and do not establish continuous uptime.
