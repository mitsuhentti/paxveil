# PAXVEIL

**See the risk. Choose the fix.**

PAXVEIL analyzes Python dependencies using official advisory and package sources, saves reports and models update options. The browser and Telegram bot share an authenticated API and project database. PAXVEIL Watch schedules follow-up checks; FixLab compares actual metadata resolutions; Fire Drill searches saved inventories for a CVE.

[Русское руководство пользователя](docs/USER_GUIDE_RU.md) · [Project status](PROJECT_STATUS.md) · [Deployment](docs/DEPLOYMENT.md) · [Portfolio case](docs/PORTFOLIO.md).

The application has run locally on Windows against PostgreSQL and real OSV, PyPI, deps.dev, FIRST EPSS and CISA KEV data. Reports preserve source failures, uncertain versions and provenance. A report with no known findings describes the checked versions and available sources at its timestamp.

## Features

- Upload `requirements.txt`, `poetry.lock` or `uv.lock`, up to 1 MiB and 300 dependency rows. Select Python and platform for environment markers.
- Save projects, rescan, inspect immutable history and known graph edges, and record finding status changes.
- See advisory aliases, CVSS, dated EPSS, CISA KEV and explained priority factors.
- Compare Minimal Change, Balanced and Maximum Coverage in FixLab. Real PyPI releases are validated, uv resolves binary metadata, and the proposed versions are queried in OSV again.
- Run Fire Drill against owner-scoped inventories, with confirmed, possible, no-match and insufficient-data outcomes.
- Enable Watch and configure categories, priority thresholds, IANA timezone, quiet hours and digests.
- Use Telegram menus, upload documents, retrieve reports, manage projects and subscriptions, and link a web account with a short-lived one-use code.

The CLI uses the same real scanner. From `backend`, with the project Python environment active:

```powershell
python -m paxveil.cli ..\examples\browser\requirements.txt --python 3.11 --platform linux
```

It writes a JSON report without saving a web project. Exit code 0 means complete recorded-version coverage with no known findings, 1 means findings with that coverage, and 2 means incomplete analysis or invalid input.

## Native Windows startup

Use **PowerShell 7 (`pwsh`)**, Python 3.11, Node.js 24/npm and PostgreSQL 18. All three PowerShell scripts require version 7. Existing system tools are reused; project dependencies and the separate database cluster stay in project-owned directories. [AUDIT.md](docs/AUDIT.md) records the inspected machine and official installation links.

For a **fresh checkout**, from the repository root in PowerShell 7:

```powershell
.\scripts\init.ps1
.\scripts\start.ps1
```

The complete fresh bootstrap has not been executed as one end-to-end installation. Re-preparing the existing runtime with `init.ps1 -RuntimeDirectory` completed twice, retaining its cluster and Telegram token; locked dependencies, `npm ci` and production build passed. Startup and ordinary shutdown also passed outside Windows isolation. See [operational validation](docs/OPERATIONS_VALIDATION.md).

Open [PAXVEIL](http://localhost:3000), register a local account and upload [examples/browser/requirements.txt](examples/browser/requirements.txt). It contains the genuine public pin `requests==2.31.0`; its code is never installed. API documentation is available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

Store the owner's BotFather token only in `TELEGRAM_BOT_TOKEN` in the ignored local `.env`. Restart with Telegram enabled:

```powershell
.\scripts\stop.ps1
.\scripts\start.ps1 -Telegram
```

This development workspace already uses an external runtime at `work/runtime`, beside `outputs`. From `outputs/paxveil`, use the matching directory for both commands:

```powershell
.\scripts\stop.ps1 -RuntimeDirectory '..\..\work\runtime'
.\scripts\start.ps1 -Telegram -RuntimeDirectory '..\..\work\runtime'
```

Keep one runtime and one polling process. If the application is already running, open its URL. A new start requires stopping the existing instance. To re-prepare or update this environment after stopping it, use `.\scripts\init.ps1 -RuntimeDirectory '..\..\work\runtime'`; its existing cluster and token are preserved.

Ordinary `stop.ps1` succeeded in the final run outside Windows isolation. Earlier sandbox restrictions blocked PostgreSQL control signaling; the explicit development fallback, `stop.ps1 -ForceDatabase`, is documented in [troubleshooting](docs/DEPLOYMENT.md#troubleshooting-native-processes). It forces the verified project-owned process tree and requires WAL recovery on the next start.

## Verified outcomes

A live scan of five pinned public dependencies returned **12 findings after advisory alias deduplication**. Balanced and Maximum Coverage actually resolved five packages, then queried OSV for those proposed versions and returned zero known findings. Minimal Change reported insufficient data for an eligible proposal. These are time-specific observations, not fixed UI numbers or proof of application compatibility.

A separate live API flow saved a `requests==2.31.0` project with three known findings, confirmed `CVE-2024-35195`, persisted Watch settings and denied a foreign owner's access. The real browser used the running API for upload, reports, history, settings and responsive checks at 390 pixels.

The final backend suite reported **122 passed and 2 intentional public-source skips**. The current-runtime launcher returned HTTP 200 for API and web and started the worker and genuine bot. Ordinary shutdown completed successfully outside Windows isolation. After restart, the QA project, one saved scan, three finding states and subscription row retained the same state hash. An earlier isolated run also tested force-stop/WAL recovery. Evidence:

- [Final automated checks](docs/TEST_RESULTS.md), [operational validation](docs/OPERATIONS_VALIDATION.md) and [runtime measurements](docs/RUNTIME_VALIDATION.json).
- [Core/FixLab live reports](docs/CORE_VALIDATION.json) and [live API acceptance](docs/LIVE_ACCEPTANCE.json).
- [Browser validation](docs/FRONTEND_VALIDATION.md), [real screenshots](docs/screenshots/) and [bounded independent review](docs/REVIEW.md).
- [Backend dependency audit](docs/SELF_AUDIT.json) and [npm audit](docs/NPM_AUDIT.json).

The owner's token for [@PAXVEIL_Bot](https://t.me/PAXVEIL_Bot) passed Telegram `getMe`, and real polling started on 11 October 2026. The owner confirmed that `/start` displayed the menu in their actual Telegram client; bot logs recorded two handled updates. Human acceptance of uploads, linking, reports and Watch remains pending; follow [TELEGRAM.md](docs/TELEGRAM.md). Automated Telegram updates use controlled fixtures for those broader handler/API checks.

## Analysis and deployment limits

A flat file does not establish every installed transitive version; missing inventory and graph edges are disclosed. Poetry lock alone does not identify project roots without `pyproject.toml`, so FixLab reports that limitation. The metadata resolver targets x86_64. Uploaded code, package builds and application tests never run. A vulnerable library version does not establish runtime reachability or exploitation in the user's application. Details: [CORE.md](docs/CORE.md).

Watch and delivery require the worker and network to remain available. A phone cannot open this computer's `localhost`. Compose is prepared but was not executed because Docker is unavailable on this machine. The standalone Playwright runner was blocked by Windows IPC/fork restrictions; in-app browser automation did execute. No public service, paid resource or external repository was created.

## Repository layout

| Path | Responsibility |
|---|---|
| `backend/paxveil` | FastAPI, authentication, models, durable worker, notification outbox, ETL and CLI |
| `backend/paxveil/core` | Parsers, official sources, prioritization, Fire Drill and FixLab |
| `backend/paxveil/bot` | aiogram menus, documents, projects and settings |
| `backend/migrations` | Alembic schema and analytical SQL views |
| `frontend` | Next.js/React/TypeScript, dark/light themes and SVG brand |
| `backend/tests`, `frontend/tests` | Automated checks and portable browser scenarios |
| `scripts`, `docs` | Startup tools, live validation, evidence and documentation |
| `compose.yaml`, `.github/workflows` | Container topology and CI configuration |

[Architecture](docs/ARCHITECTURE.md) · [Core](docs/CORE.md) · [API contract](docs/CONTRACT.md).

PostgreSQL implements queue leases, fencing, retries and the Watch schedule, avoiding extra Redis/Celery/Airflow services for the measured local scope. ETL retains public snapshots and provenance, normalizes operational records, checks data quality and exposes SQL analytical views. A future orchestrator can invoke these real jobs.

Secrets, database files, runtime and installed dependencies are excluded from Git. Public release requires a license decision and final artifact review. Public operation requires verified TLS, backup/restore, account quotas, retention and data-handling rules; see [DEPLOYMENT.md](docs/DEPLOYMENT.md).
