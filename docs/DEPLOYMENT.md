# PAXVEIL deployment and operations

The selected zero-budget deployment runs the Telegram bot on the owner's Windows computer. Telegram users connect through Telegram; the computer needs outbound HTTPS and does not need a public IP address, domain or open router ports. Availability depends on the computer staying awake, its network connection and the application processes. No hosting account or paid resource has been created.

Native startup, ordinary shutdown and restart have recorded evidence. A PostgreSQL backup restored into a separate database with all table fingerprints matching, and real concurrent queue claims passed. Full fresh bootstrap, Docker execution and remote GitHub Actions remain unverified.

## Native Windows prerequisites

Use **PowerShell 7 (`pwsh`)**; all three scripts declare `#requires -Version 7.0`. Windows PowerShell 5.1 is not a supported launcher. The application uses Python 3.11 with `venv`, Node.js 24/npm, and PostgreSQL 18 binaries including `initdb`, `postgres`, `pg_isready` and `pg_ctl`. Dependency locks are `backend/requirements.lock` and `frontend/package-lock.json`.

If `pwsh` is unavailable in a new environment, use Microsoft's [PowerShell 7 installation guide](https://learn.microsoft.com/en-us/powershell/scripting/install/install-powershell-on-windows). Installing a system component remains an owner-approved setup action; these scripts do not install PowerShell.

Allow disk space for venv/npm, the frontend build, PostgreSQL and source-snapshot growth. [AUDIT.md](AUDIT.md) contains measured host details and official installation links. Project startup does not install system components or require administrator rights.

## Fresh checkout: designed bootstrap path

From the repository root in PowerShell 7:

```powershell
.\scripts\init.ps1
.\scripts\start.ps1
```

The whole fresh bootstrap from empty checkout/new environment/new cluster has not yet been executed end to end. Existing-runtime initialization completed twice: backend lock satisfied, `npm ci` installed 55 packages with zero audited vulnerabilities, and production build passed. See [OPERATIONS_VALIDATION.md](OPERATIONS_VALIDATION.md).

If PostgreSQL is installed elsewhere, provide its existing binary directory:

```powershell
.\scripts\init.ps1 -PostgresBin 'D:\PostgreSQL\18\bin'
```

`init.ps1` creates `runtime/venv`, installs the backend lock, runs `npm ci` and builds the frontend. Its optional `-RuntimeDirectory` applies to the venv, npm cache and cluster. It generates a missing `.env` with independent random database/bot secrets and initializes its own `pgdata` with SCRAM. Existing secrets, including the Telegram token, and an initialized cluster are preserved. For an older native `.env` missing `POSTGRES_PASSWORD`, the initializer adds that Compose setting from the password in its own local project DSN without exporting it. The default cluster listens only on `127.0.0.1:55432`; unrelated PostgreSQL data is not used.

`start.ps1` refuses occupied project ports and an existing process manifest. It starts its PostgreSQL, waits for readiness, verifies the expected cluster PID, creates the project database if needed and applies Alembic. It then starts API, worker, production frontend and optional bot, and waits for API/web HTTP 200. Processes use hidden windows; stdout/stderr logs and a PID/start-time manifest are written to runtime.

| Address | Purpose |
|---|---|
| `http://localhost:3000` | Browser UI |
| `http://127.0.0.1:8000/docs` | OpenAPI |
| `http://127.0.0.1:8000/api/health` | API/database readiness |
| `127.0.0.1:55432` | Project-owned native PostgreSQL |

Ordinary stop preserves database files and source snapshots:

```powershell
.\scripts\stop.ps1
```

The tested development workspace uses `work/runtime`, beside `outputs`, rather than repository-local `runtime`. From `outputs/paxveil`:

```powershell
.\scripts\stop.ps1 -RuntimeDirectory '..\..\work\runtime'
.\scripts\start.ps1 -Telegram -RuntimeDirectory '..\..\work\runtime'
```

Use that directory consistently. To re-prepare this existing environment after stopping it, run:

```powershell
.\scripts\init.ps1 -RuntimeDirectory '..\..\work\runtime'
```

The existing cluster and token are retained. Then start with the same runtime directory. A new checkout uses the normal commands without `-RuntimeDirectory`.

## Automatic local operation

The user-level launcher is `scripts/autostart.ps1`. Enable it for the existing workspace:

```powershell
.\scripts\autostart.ps1 -Mode Enable -RuntimeDirectory '..\..\work\runtime' -BotOnly
.\scripts\autostart.ps1 -Mode Status -RuntimeDirectory '..\..\work\runtime'
```

It uses the current Windows user's login startup entry and `scripts/supervise-native.ps1` to supervise the project processes, with an optional bot-only launch. It requires no administrator-installed service. The supervisor invokes the daily backup helper and keeps logs in runtime. A login startup entry cannot run while the computer is powered off; after reboot the owner must sign in. Sleep or loss of connectivity interrupts polling and delivery.

```powershell
.\scripts\autostart.ps1 -Mode Disable -RuntimeDirectory '..\..\work\runtime'
.\scripts\stop.ps1 -RuntimeDirectory '..\..\work\runtime'
```

Normal stop sets the disabled marker before stopping the verified supervisor and its owned services. A retained login entry then remains inactive until Enable is used. The supervisor verifies recorded process identities and does not take ownership of unrelated processes. Its execution evidence is recorded separately when the final launch is verified.

## Troubleshooting native processes

The stop script verifies each recorded process start time before terminating its project-owned tree. The timestamp comparison supports PowerShell's automatic JSON date parsing. Normal PostgreSQL shutdown uses `pg_ctl`; failures retain the manifest for inspection and retry.

Ordinary `stop.ps1`, without `-ForceDatabase`, succeeded in the final run outside Windows isolation. That run showed no earlier autovacuum-worker startup warning after more than one minute; this is a bounded maintenance observation. In an earlier sandbox run, PostgreSQL control signaling was blocked. An explicit fallback remains available for the verified **development** cluster:

```powershell
.\scripts\stop.ps1 -RuntimeDirectory '..\..\work\runtime' -ForceDatabase
```

Use the same runtime directory as startup; omit it only for repository-local runtime. The flag attempts normal PostgreSQL stop first, then force-terminates only its verified process tree if control signaling fails. The next start requires WAL recovery. Both the earlier crash-recovery check and final restart retained the QA project's state hash, one saved scan, three finding states and subscription row. See [runtime evidence](RUNTIME_VALIDATION.json) and [operational notes](OPERATIONS_VALIDATION.md). The separate backup restoration described below verifies recovery from a dump without changing the working cluster.

If a startup stage fails, inspect the selected runtime logs and use the matching stop script; the manifest remains available. If a port is occupied, identify its owner before doing anything. Manually started services are not automatically owned by a manifest; never stop unrelated processes by name. Keep one polling process per Telegram token.

## Telegram configuration

Bot creation requires the owner's [@BotFather](https://t.me/BotFather) account. Store the token only in repository-root `.env` under `TELEGRAM_BOT_TOKEN`. `PAXVEIL_BOT_KEY` is a separate random service secret shared by API and bot; fresh initialization generates it. Do not put either value in chat, Git, screenshots or command-line arguments.

After configuration use `start.ps1 -Telegram`. The owner's [@PAXVEIL_Bot](https://t.me/PAXVEIL_Bot) passed `getMe`, and real polling started on 11 October 2026. The owner confirmed the menu after `/start` in their actual client; two handled updates were logged. Uploads, linking, reports and Watch still require the [live checklist](TELEGRAM.md#verification-boundary-and-live-acceptance-checklist). Browser Settings issues a one-use code; `/link CODE` binds the Telegram identity to that signed-in web owner.

API, bot and worker need network access to their configured services. Polling and Watch delivery require outbound HTTPS to Telegram. Bot startup removes an existing webhook without dropping pending updates; do not run a second instance or a deployment webhook simultaneously for the token. Watch stops scheduling/delivering when worker is stopped. A localhost report URL must be opened on this computer; a phone requires a separately deployed reachable HTTPS URL.

## Docker Compose: portable bot deployment

This path requires Docker Engine/Desktop and Compose v2. Docker was unavailable, so the supplied Dockerfiles and Compose topology have not run on this machine. In a fresh Linux checkout, create `.env` from `.env.example`, replace all secret placeholders with independent random values and configure the Telegram token when using the bot. Do not leave `CHANGE_ME` or `GENERATE_RANDOM_64_HEX_CHARACTERS`.

Compose overrides `DATABASE_URL` with the private `db:5432` address and persists PostgreSQL in a named volume. Backend/bot use `PAXVEIL_API_URL=http://api:8000`. `PAXVEIL_WEB_URL` is the human-facing address, locally `http://localhost:3000`; an internal container hostname must not be shown as the report URL.

The bot-only stack consists of PostgreSQL, the migration step, API, worker and one polling bot. It publishes no host ports. From the repository root in a Docker environment:

```text
docker compose --profile telegram config --quiet
docker compose --profile telegram up --build --wait -d api worker bot
docker compose ps
docker compose logs --tail 100 api worker bot
```

The quiet config check avoids printing resolved secrets. PostgreSQL health gates migrations; successful migrations gate API; API/database health gates worker and bot. Application containers use a nonroot user and dropped capabilities. Backend root filesystems are read-only; the cache volume and bounded temporary directory remain writable. Logs rotate at 10 MiB with three files per service. An init process reaps children, process limits are 128, and normal stop gives application services 30 seconds and PostgreSQL 60 seconds. These settings follow the [Compose service reference](https://docs.docker.com/reference/compose-file/services/). Worker and bot startup is a process check; verify an actual completed job and Telegram response afterward.

The optional `web` profile builds and starts the browser UI on host loopback only:

```text
docker compose --profile web --profile telegram up --build -d
```

For local OpenAPI inspection, merge `compose.local.yaml`; it adds only `127.0.0.1:8000`. Profiles control optional services as described in the [Docker documentation](https://docs.docker.com/compose/how-tos/profiles/). The native runtime is already available and does not require installing Docker.

```text
docker compose --profile telegram --profile web down
```

Named volumes remain. `down -v` deletes database/cache data and is not part of ordinary shutdown. Include every enabled profile when stopping. At first execution, verify upload, completed analysis, FixLab, Fire Drill, Watch, Telegram and persistence after restart. Native acceptance does not substitute for these container checks. The supplied CI prepares a disposable container check; no remote CI run has yet been observed.

## Updates and backups

Before upgrading, create a private PostgreSQL backup outside the repository and retain `.env` separately with owner-only access. A database backup contains uploaded manifests, project records, session hashes and Telegram identifiers. It must not enter Git, release archives or portfolio attachments. Copying native `pgdata` requires a verified clean shutdown and remains PostgreSQL-version-specific.

`scripts/database-ops.py` uses the existing project Python and matching PostgreSQL client tools. In a fresh checkout with its prepared venv:

```powershell
.\runtime\venv\Scripts\python.exe scripts/database-ops.py backup --env .env --pg-bin 'C:\Program Files\PostgreSQL\18\bin' --directory '..\paxveil-private-backups'
```

Use the external venv path when the launcher uses `-RuntimeDirectory`. The development workspace uses `..\..\work\runtime\venv\Scripts\python.exe` and stores backups in `..\..\work\runtime\backups`. The backup destination is deliberately rejected if it is inside the checkout.

The custom dump and private JSON manifest share a basename. Row fingerprints are taken in the exported snapshot used by `pg_dump`; ongoing writes do not produce inconsistent comparison evidence. Credentials travel through process environment variables, never tool arguments or public evidence. See [PostgreSQL pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html).

After successful creation, the helper rotates recognized, checksum-valid backup pairs older than seven days. `--retain-days` changes that policy. Failed creation retains earlier backups. Consequently, a stalled backup service can keep older copies until a later successful backup; check the latest success timestamp. Linux creates owner-only files/directories. On Windows, use a directory with an owner-only inherited ACL; the helper does not silently change Windows account permissions. A local backup protects against accidental data loss, while a private copy on another device is needed for disk failure.

Verify a selected dump with its matching manifest:

```powershell
.\runtime\venv\Scripts\python.exe scripts/database-ops.py verify-backup --env .env --pg-bin 'C:\Program Files\PostgreSQL\18\bin' --archive '..\paxveil-private-backups\BACKUP_NAME.dump' --evidence docs/BACKUP_VALIDATION.json
```

The verifier checks the archive checksum, creates a uniquely named database marked as disposable, restores with `--exit-on-error`, compares every public-table row fingerprint, and removes only the database with the matching marker. It has no option to overwrite the working database. The database role needs permission to create a database. [PostgreSQL pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html) documents the restore tool.

The actual **12 October 2026** run restored a 74,595-byte snapshot: **19 tables and 161 rows matched**, and the disposable database was removed. This establishes one complete logical dump/restore on PostgreSQL 18.6; it does not establish off-device disaster recovery. [BACKUP_VALIDATION.json](BACKUP_VALIDATION.json) contains sanitized evidence.

Stop the application, update to the selected source revision and run `init.ps1` with the same `-RuntimeDirectory` used for startup, if external. This installs from dependency locks, rebuilds frontend and retains the cluster/configured secrets. The launcher applies forward migrations. Check health, saved projects/history/subscriptions and `alembic check` afterward. Application rollback must account for the migrated schema; do not erase data to resolve a compatibility problem.

For Compose, back up and stop before rebuilding/updating; then enable the Telegram profile as needed. Do not change PostgreSQL major versions by replacing an image tag without a database migration plan. The helper's `--postgres-container CONTAINER_ID` uses tools from an existing same-instance PostgreSQL container; Python still needs private database access. It is used by the prepared CI job and has not run locally because Docker is unavailable.

## PostgreSQL concurrency verification

```powershell
.\runtime\venv\Scripts\python.exe scripts/database-ops.py verify-concurrency --env .env --evidence docs/POSTGRES_CONCURRENCY_VALIDATION.json
```

This creates and migrates a separate marked database, uses eight threads with distinct database sessions, and removes it after verification. The actual 12 October run made 24 simultaneous enqueue requests that returned one scan job; 40 claim attempts claimed 24 pending jobs exactly once. Expiring a lease produced a new claim token, and executing the stale claim could not overwrite the successful successor. Analysis used a controlled in-memory report and made zero source queries. This verifies PostgreSQL locking and claim fencing, rather than scan throughput or external API capacity. [POSTGRES_CONCURRENCY_VALIDATION.json](POSTGRES_CONCURRENCY_VALIDATION.json) records the counts.

CI now prepares the same queue and dump/restore checks, uploads sanitized evidence, verifies migrations, checks backend code and builds the frontend. A separate job builds private API/worker containers and the optional web image. CI databases and volumes are disposable and contain only test data. These jobs need an uploaded GitHub repository before they can provide remote run evidence.

## Logs, jobs and ETL

Native logs are stored in the selected runtime. Avoid Telegram HTTP debug logging: the Bot API request path contains a token. API requests enqueue durable scan/FixLab jobs rather than holding the client connection during external work. Worker timeouts, retry limits, lease recovery and fencing are implemented. Watch defaults to six-hour checks.

From `backend`, using the project's Python:

```text
python -m paxveil.etl quality
python -m paxveil.etl metrics
python -m paxveil.etl refresh
```

`quality` checks orphan scans, duplicate findings, priority bounds and completed scans without reports. `metrics` reads the SQL view. `refresh` enqueues watched projects for real source queries; avoid using it to generate repeated public API load. Alembic creates `scan_risk_metrics` and `notification_delivery_metrics`.

The measured runtime sample contains 20 sequential local API-health requests: median 2.14 ms, p95 2.56 ms, maximum 6.07 ms. Twenty web-HTML requests measured median 2.65 ms, p95 3.42 ms, maximum 6.07 ms. These measurements cover lightweight local endpoints, not scan throughput or concurrent capacity. [RUNTIME_VALIDATION.json](RUNTIME_VALIDATION.json) records the scope; [CORE_VALIDATION.json](CORE_VALIDATION.json) records real scan/cache observations.

An idle memory snapshot summed 646.66 MiB of working sets and 457.84 MiB of private commit for readable project process trees. Working-set sums double-count shared pages, and several children were unreadable, so these are partial observed sums rather than total or peak application memory. [MEMORY_SNAPSHOT.json](MEMORY_SNAPSHOT.json) provides the method and component counts.

## Free operation and later hosting

The selected setup adds no Telegram or hosting subscription. It uses the owner's computer and internet connection. The bot remains reachable through its public Telegram username while that machine runs. Do not change router forwarding or expose PostgreSQL/API to make the bot public. Polling is outbound; use one polling process for the token.

An independent host is useful when the computer must be turned off. Free provider offers have account, capacity, sleep and persistence conditions; choose and verify those conditions before migration. A free web service that sleeps or expires its database is unsuitable for uninterrupted polling and durable Watch history. The prepared bot-only container package can move to a suitable Linux host later. Linux ARM execution has not been tested; the FixLab resolver explicitly models its documented x86_64 target environments.

Public browser access is a separate deployment: add verified HTTPS termination, an exact `ALLOWED_ORIGINS`, `SECURE_COOKIES=true` and a reachable HTTPS `PAXVEIL_WEB_URL`. No public browser deployment has been created. Telegram operation does not depend on a public browser URL.

Source lookups send package names/versions to the source APIs; Telegram receives documents/messages through its service. The public bot's privacy and deletion controls explain stored data and private backup retention. Review usage, failures, free disk space and the latest backup success as the number of users grows. Current endpoint measurements do not establish a supported number of concurrent users.
