# PAXVEIL project status

Snapshot: **12 October 2026**. Source repository: `outputs/paxveil`. The prepared development runtime is `work/runtime`, beside `outputs`; it contains the project Python environment, PostgreSQL cluster, logs and process manifest. Secrets remain in the ignored repository-root `.env` and are not included here.

The interface and brand were redesigned on 11-12 October: a constructed P mark, light/cobalt and dark themes, revised Russian copy and responsive working screens. The new icon, name and description were applied to the configured Telegram bot and verified through its API. The affected bot tests reported 24 passes; production frontend build, browser checks and final ordinary stop/start passed. See [DESIGN_REVIEW.md](docs/DESIGN_REVIEW.md) and [profile evidence](docs/TELEGRAM_BRAND_VALIDATION.json). The full 122-pass/2-skip backend run below remains dated 11 October.

## Implemented behavior

| Area | Implementation |
|---|---|
| API and storage | FastAPI, owner-scoped accounts/sessions/objects, PostgreSQL/SQLAlchemy, Alembic, immutable scan and finding-status history |
| Parsing | Three Python manifest formats, exact versions, selected-environment markers, uncertainty and explicit unsupported constructs |
| Sources | Real OSV/PyPI/deps.dev/EPSS/CISA clients, bounds, pacing, timeouts, retries, TTL cache and provenance snapshots |
| Triage | Separate CVSS/EPSS/KEV signals, explained policy score and advisory alias deduplication |
| FixLab | Three strategies, verified PyPI targets, uv wheel-metadata resolution and actual OSV rescans |
| Fire Drill | CVE/alias lookup, saved owner inventory, known paths and explicit certainty levels |
| Watch | Durable schedule, subscriptions, categories, thresholds, quiet hours, IANA timezone and digest settings |
| Delivery | Outbox fingerprints, retries, delivery-time preference checks, attempt journal and claim fencing |
| Telegram | Private-chat menus, uploads/reports, projects, FixLab, Fire Drill, Watch, settings, one-use linking and confirmation-bound deletion |
| Browser | Upload/report/history/graph/status flows, Watch/settings, dark/light theme, mobile navigation and custom SVG assets |
| Operations | Native Windows launchers, Compose, nonroot application containers, health checks, structured logs, dependency locks and CI configuration |
| Data Engineering | Normalized relations, constraints/indexes, historical reports/sources, durable incremental jobs, quality checks and SQL analytical views |

## Executed validation

- The final backend run completed with **122 passed, 2 intentional public-source skips and one framework deprecation warning in 32.45 seconds**. Ruff passed on source and tests. [TEST_RESULTS.md](docs/TEST_RESULTS.md) contains scope and exact output.
- OSV, PyPI, deps.dev and FIRST EPSS answered genuine probes. Missing enrichment stays visible. A live five-pin scan returned 12 deduplicated findings; Balanced and Maximum Coverage resolved five pins with zero known findings in subsequent OSV checks. Minimal Change had no eligible proposal.
- Live API acceptance exercised bad uploads, persistence, asynchronous processing, Fire Drill, Watch and foreign-owner rejection.
- Real browser automation exercised running product responses and a 390 × 844 mobile viewport. Screenshots are in `docs/screenshots`.
- Handler/API tests use controlled Telegram updates. The owner configured a real token; `@PAXVEIL_Bot` passed `getMe`, and polling started on 11 October. The owner confirmed that `/start` displayed the menu in their real client; two handled updates were recorded. Upload/link/report/Watch human acceptance remains pending.
- Re-preparation with `init.ps1 -RuntimeDirectory` completed twice against the existing runtime: backend lock satisfied, `npm ci` installed 55 packages with zero audited vulnerabilities, and production build passed. The cluster and configured token were preserved. A missing Compose `POSTGRES_PASSWORD` setting was backfilled into the ignored `.env` from the existing project database DSN.
- The native launcher started the existing runtime with API/web HTTP 200, worker and genuine bot. Outside Windows isolation, PostgreSQL ran without the earlier autovacuum startup warnings and ordinary `stop.ps1` completed successfully without force. An earlier isolated run had tested project-owned force-stop/WAL recovery. After the final restart, the QA project, one scan, three finding states and subscription row kept the same state hash.
- Twenty sequential local API-health samples measured median **2.14 ms**, p95 **2.56 ms**, max **6.07 ms**. Twenty web-HTML samples measured median **2.65 ms**, p95 **3.42 ms**, max **6.07 ms**. These are bounded local observations, not a load test or production SLA.
- One idle snapshot of readable project process trees summed **646.66 MiB working sets** and **457.84 MiB private commit**. Some child processes were unreadable and working-set sums double-count shared pages; this is not complete application memory or peak RSS. [MEMORY_SNAPSHOT.json](docs/MEMORY_SNAPSHOT.json) records component counts and limitations.

Evidence: [automated checks](docs/TEST_RESULTS.md), [operational validation](docs/OPERATIONS_VALIDATION.md), [runtime JSON](docs/RUNTIME_VALIDATION.json), [CORE_VALIDATION.json](docs/CORE_VALIDATION.json), [LIVE_ACCEPTANCE.json](docs/LIVE_ACCEPTANCE.json), [API_PROBE.json](docs/API_PROBE.json), [browser checks](docs/FRONTEND_VALIDATION.md), [review](docs/REVIEW.md).

## Remaining verification and deployment work

| Item | Current boundary and next action |
|---|---|
| Human Telegram acceptance | Real `/start` menu confirmed by owner; uploads, linking, reports, additional menus and Watch still require the live checklist in [TELEGRAM.md](docs/TELEGRAM.md) |
| Fresh native bootstrap | Existing-runtime `init.ps1` passed twice; the entire path from empty checkout/new environment/new cluster remains untested |
| Containers | Docker/Compose unavailable locally; build and execute the prepared topology in a Docker environment |
| Standalone browser runner | Portable scenarios exist; Windows IPC/fork restrictions blocked the standalone runner. In-app browser validation executed |
| Remote CI | Workflow prepared; no external repository or GitHub Actions execution |
| Public operation | No public service. Needs owner approval, TLS, registration policy, quotas, backup/restore, retention and infrastructure acceptance |
| Multiple-worker concurrency | Fencing paths covered in bounded tests/static review; real PostgreSQL concurrency and paused-process fault injection remain. Shared reference ingestion can hit uniqueness conflicts and rollback/retry |
| Behavioral compatibility | FixLab checks metadata and advisories, not application behavior, configuration or reachability |
| Publication | Preliminary search found no obvious software-name collision; domain/trademark clearance and source license are still decisions before publication |

## Known product limits

Inputs are limited to 1 MiB and 300 dependencies. Unpinned, uncertain and unsupported requirements are unknown. Missing transitives cannot be reconstructed from a partial manifest. Poetry lock lacks project-root constraints without `pyproject.toml`. FixLab resolves x86_64 wheel metadata without sdist builds, installation or uploaded code execution. Telegram uploads currently use Python 3.11/Linux; choose a different environment through the web.

Reports depend on source date and availability. Watch rejects an incomplete OSV lookup as a reliable baseline and suppresses source-availability-only changes. Telegram delivery can repeat after a crash between remote acknowledgement and the database commit; external exactly-once delivery is not claimed.

Long-lived deployments need snapshot retention, expired-session cleanup and account storage quotas. Rate limits are process-local. Localhost report URLs are reachable on the host computer; a phone needs a separately deployed HTTPS address. Continuous Watch needs a running database, worker and network.

## Continue in a new session

Read this file, [TEST_RESULTS.md](docs/TEST_RESULTS.md), [OPERATIONS_VALIDATION.md](docs/OPERATIONS_VALIDATION.md), [ARCHITECTURE.md](docs/ARCHITECTURE.md) and [REVIEW.md](docs/REVIEW.md). Do not print `.env` or Telegram token-bearing URLs. Preserve the existing cluster and use the same runtime path when re-preparing the environment.

All scripts require **PowerShell 7 (`pwsh`)**. From `outputs/paxveil`, for this existing runtime:

```powershell
.\scripts\stop.ps1 -RuntimeDirectory '..\..\work\runtime'
.\scripts\start.ps1 -Telegram -RuntimeDirectory '..\..\work\runtime'
```

For dependency re-preparation or updates, after stopping the services:

```powershell
.\scripts\init.ps1 -RuntimeDirectory '..\..\work\runtime'
```

Then use the matching start command. This reuses the cluster and configured secrets; an older native `.env` can receive the missing Compose password setting from its own local DSN.

Ordinary shutdown passed outside isolation. If database shutdown reports the earlier sandbox signaling failure, only this verified development cluster may use the explicit fallback:

```powershell
.\scripts\stop.ps1 -RuntimeDirectory '..\..\work\runtime' -ForceDatabase
```

The next start performs PostgreSQL WAL recovery. This fallback is not a substitute for verified production shutdown/backup. Startup refuses occupied local ports before launching anything. If processes were started manually, establish their project ownership first; never stop a process solely by executable name.

Addresses: web `http://localhost:3000`, API docs `http://127.0.0.1:8000/docs`, health `http://127.0.0.1:8000/api/health`, PostgreSQL `127.0.0.1:55432`. Logs and `processes.json` are in the selected runtime.

From `backend`, using the project's Python environment:

```powershell
python -m ruff check paxveil tests
python -m pytest -q -m 'not integration'
python -m alembic upgrade head
python -m alembic check
python -m paxveil.etl quality
python -m paxveil.etl metrics
```

From `frontend`: `npm run typecheck` and `npm run build`. Public integration calls opt in through `PAXVEIL_LIVE_TESTS=1`; avoid repeated external load. `scripts/validate-live.py` creates a separate local QA account and projects using public dependencies. Existing browser/automation QA accounts are test-owned records, not real customer data.

The next engineering stage is human Telegram acceptance, then a fresh/bootstrap and Compose check plus backup restoration in a separate environment. Public hosting, external repositories and paid resources require the owner's decision.
