# PAXVEIL deployment and operations

Native Windows startup reuses existing Python, Node.js and PostgreSQL. The prepared runtime passed re-preparation twice, startup, ordinary shutdown outside Windows isolation and restart with recorded evidence. Full fresh bootstrap and Docker execution remain unverified. No public server or paid resource has been created.

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

## Troubleshooting native processes

The stop script verifies each recorded process start time before terminating its project-owned tree. The timestamp comparison supports PowerShell's automatic JSON date parsing. Normal PostgreSQL shutdown uses `pg_ctl`; failures retain the manifest for inspection and retry.

Ordinary `stop.ps1`, without `-ForceDatabase`, succeeded in the final run outside Windows isolation. That run showed no earlier autovacuum-worker startup warning after more than one minute; this is a bounded maintenance observation. In an earlier sandbox run, PostgreSQL control signaling was blocked. An explicit fallback remains available for the verified **development** cluster:

```powershell
.\scripts\stop.ps1 -RuntimeDirectory '..\..\work\runtime' -ForceDatabase
```

Use the same runtime directory as startup; omit it only for repository-local runtime. The flag attempts normal PostgreSQL stop first, then force-terminates only its verified process tree if control signaling fails. The next start requires WAL recovery. Both the earlier crash-recovery check and final restart retained the QA project's state hash, one saved scan, three finding states and subscription row. These bounded observations do not establish long-term production reliability or backup recoverability. See [runtime evidence](RUNTIME_VALIDATION.json) and [operational notes](OPERATIONS_VALIDATION.md).

If a startup stage fails, inspect the selected runtime logs and use the matching stop script; the manifest remains available. If a port is occupied, identify its owner before doing anything. Manually started services are not automatically owned by a manifest; never stop unrelated processes by name. Keep one polling process per Telegram token.

## Telegram configuration

Bot creation requires the owner's [@BotFather](https://t.me/BotFather) account. Store the token only in repository-root `.env` under `TELEGRAM_BOT_TOKEN`. `PAXVEIL_BOT_KEY` is a separate random service secret shared by API and bot; fresh initialization generates it. Do not put either value in chat, Git, screenshots or command-line arguments.

After configuration use `start.ps1 -Telegram`. The owner's [@PAXVEIL_Bot](https://t.me/PAXVEIL_Bot) passed `getMe`, and real polling started on 11 October 2026. The owner confirmed the menu after `/start` in their actual client; two handled updates were logged. Uploads, linking, reports and Watch still require the [live checklist](TELEGRAM.md#verification-boundary-and-live-acceptance-checklist). Browser Settings issues a one-use code; `/link CODE` binds the Telegram identity to that signed-in web owner.

API, bot and worker need network access to their configured services. Polling and Watch delivery require outbound HTTPS to Telegram. Bot startup removes an existing webhook without dropping pending updates; do not run a second instance or a deployment webhook simultaneously for the token. Watch stops scheduling/delivering when worker is stopped. A localhost report URL must be opened on this computer; a phone requires a separately deployed reachable HTTPS URL.

## Docker Compose: prepared topology

This path requires Docker Engine/Desktop and Compose v2. Docker was unavailable, so the supplied Dockerfiles and Compose topology have not run on this machine. In a fresh Linux checkout, create `.env` from `.env.example`, replace all secret placeholders with independent random values and configure the Telegram token when using the bot. Do not leave `CHANGE_ME` or `GENERATE_RANDOM_64_HEX_CHARACTERS`.

Compose overrides `DATABASE_URL` with the private `db:5432` address and persists PostgreSQL in a named volume. Backend/bot use `PAXVEIL_API_URL=http://api:8000`. `PAXVEIL_WEB_URL` is the human-facing address, locally `http://localhost:3000`; an internal container hostname must not be shown as the report URL.

From the repository root in a Docker environment:

```text
docker compose config --quiet
docker compose up --build -d
docker compose --profile telegram up -d bot
docker compose ps
docker compose logs --tail 100 api worker bot web
```

The quiet config check avoids printing resolved secrets. A one-shot migration service waits for healthy PostgreSQL; API waits for successful migrations; worker/bot wait for API health. Application containers are nonroot with dropped capabilities. API and web host ports bind only to loopback; PostgreSQL exposes no host port.

```text
docker compose down
```

Named volumes remain. `down -v` deletes database/cache data and is not part of ordinary shutdown. At first execution, verify registration, upload, job completion, FixLab, Fire Drill, Watch, Telegram and persistence after `down`/`up`. Native acceptance does not substitute for these container checks.

## Updates and backups

Before upgrading, produce a private PostgreSQL `pg_dump` outside the repository and retain `.env` separately with owner-only access. A database backup contains uploaded manifests, project records and Telegram identifiers. Test restoring the backup to a separate cluster before changing the working instance. Copying native `pgdata` is only appropriate after a verified clean shutdown and remains PostgreSQL-version-specific.

Stop the application, update to the selected source revision and run `init.ps1` with the same `-RuntimeDirectory` used for startup, if external. This installs from dependency locks, rebuilds frontend and retains the cluster/configured secrets. The launcher applies forward migrations. Check health, saved projects/history/subscriptions and `alembic check` afterward. Application rollback must account for the migrated schema; do not erase data to resolve a compatibility problem.

For Compose, back up and stop before rebuilding/updating; then enable the Telegram profile as needed. Do not change PostgreSQL major versions by replacing an image tag without a database migration plan. Backup/restore execution remains a future operational verification.

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

## Continuous hosting requirements and cost reference

A starting planning hypothesis for a small deployment is **2 vCPU, 4 GiB RAM and 40–80 GiB SSD**, with one worker and storage headroom. This is not a tested capacity promise. Next build may need additional headroom; size the service from observed memory, job duration and actual project counts.

DigitalOcean's official pricing page checked on **11 October 2026** lists its Basic 2-vCPU/4-GiB/80-GiB plan at **$24 per month**. This is a VM price reference; domain, backups, tax and additional services are separate. Verify the offer before purchasing: [Droplet pricing](https://www.digitalocean.com/pricing/droplets). No paid resources were created.

Public operation requires verified HTTPS termination, an exact `ALLOWED_ORIGINS`, `SECURE_COOKIES=true`, a public HTTPS `PAXVEIL_WEB_URL`, private database/secrets and deliberate registration/storage quotas. Multi-instance operation needs shared rate limits and concurrent-ingestion validation. Add tested backup/restore, log rotation, source retention and worker/outbox monitoring. One bot polling instance can operate on a server; protected webhook delivery would require a separate implementation and acceptance.

Before publication, the owner chooses source licensing, retention/deletion rules for uploaded manifests and identifiers, and service terms. Source lookups send package names/versions to public source APIs; Telegram receives documents/messages sent through its service. Formal name/domain/trademark checks remain before public launch. Public deployment, external accounts and paid resources require the owner's decision.
