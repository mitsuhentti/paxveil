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

Docker/Compose execution, external CI, public hosting, concurrent PostgreSQL fault injection and backup restoration remain unverified. The final services were left running locally; continuous operation depends on the computer, processes and network remaining available.
