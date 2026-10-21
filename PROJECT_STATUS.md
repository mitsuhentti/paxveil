# PAXVEIL project status

Snapshot: **21 October 2026**. Source: `outputs/paxveil`. The prepared Windows runtime is `work/runtime`, beside `outputs`. Credentials stay in the ignored repository-root `.env`.

The owner selected free operation on their own computer. The configured [@PAXVEIL_Bot](https://t.me/PAXVEIL_Bot) uses outbound polling, with no incoming public port. The local application has been restarted normally and is running. Its availability depends on the computer, Windows session, network and processes. No cloud deployment, uptime SLA or public traffic capacity is claimed.

## Implemented

| Area | Behavior |
| --- | --- |
| Analysis | Three Python manifest formats, selected environment, explicit uncertainty and official OSV/PyPI/deps.dev/EPSS/CISA sources |
| Triage | Advisory alias deduplication, CVSS/EPSS/KEV and explained priority |
| FixLab | Three strategies, verified release metadata, uv resolution and OSV checks of proposals |
| Saved data | Owner-scoped projects, scans, graph edges, finding state/history and CVE inventory search |
| Watch | Durable schedules, comparison baselines, notification outbox, retries, quiet hours and digests |
| Public controls | Shared request counters, account job/storage quotas, retention, export and confirmed account deletion |
| Telegram | Menus, files, reports, project actions, environment defaults, privacy, export, deletion and real example scan |
| Web | Sample upload, report filters, scan links, resumable FixLab, clearer settings, light/dark themes and responsive layouts |
| Operations | Native start/stop, user-level supervisor, sign-in startup, private daily backup tooling, Compose and CI configuration |
| Data engineering | Normalized relations, provenance, constraints, ETL quality checks and SQL analytical views |

See [public resource limits](docs/PUBLIC_RESOURCES.md) and [cache lifecycle](docs/PUBLIC_CACHE.md). Current browser acceptance records 20 checks across upload, reports, FixLab, historical scan links, settings and mobile controls.

## Executed evidence

| Date | Observation |
| --- | --- |
| 21 October | Full backend suite: **178 passed, 2 intentional public-source skips, 1 Starlette/httpx warning, 46.75 seconds** |
| 21 October | TypeScript checking and production frontend build passed |
| 21 October | Real PostgreSQL: eight threads; 24 enqueues deduplicated to one job; 24 distinct claims from 24 pending jobs; lease recovery and stale-claim fencing passed |
| 21 October | PostgreSQL deletion during claim/success/failure and concurrent shared catalog upserts passed |
| 21 October | Shared request counter: exactly 11 accepted out of 64 concurrent attempts, bounded rejection and next-window recovery |
| 21 October | Normal stop/start of the existing runtime completed; application returned to service |
| 21 October | Native supervisor checker passed all 19 checks after the guard fix |
| 21 October | Browser: sample selection/cancellation, real four-second scan with three findings/five source entries, closed-filter empty state and reset |
| 21 October | Browser: FixLab survived navigation/reload; Balanced/Maximum proposed requests 2.34.2 with zero known findings; Minimal Change reported insufficient data |
| 21 October | Browser: settings dirty/save and Windows environment, mobile content width 375 pixels without overflow, Escape returning focus |
| 21 October | Browser: historical scan URL survived reload and returned to latest; readable history labels; owner-specific drafts survived navigation; quiet-hour error focused the missing field; active-route/desktop-resize menu cleanup passed |
| 21 October | Private dump restored to a disposable database: 20 tables, 251 rows, 87,355-byte archive, all fingerprints matched |
| 21 October | Current API/web HTTP 200, exact recorded process identities, supervisor/sign-in entry and backup checkpoint observed; selected runtime data, logs, private backups and secret file confirmed EFS-encrypted |
| 21 October, 13:54:43 UTC | Telegram getMe succeeded, default/Russian command lists matched all 12 commands, no webhook; earlier network failure had recovered |
| 11–12 October | Owner confirmed the actual Telegram `/start` menu and later `/privacy`, `/environment` and `/projects` |
| Earlier live source runs | Five pinned dependencies produced 12 deduplicated findings; Balanced/Maximum proposals resolved five pins and returned zero known OSV findings |

The source results apply to their recorded dates, versions and source coverage. Current EFS inspection covered 1,381 PostgreSQL files, four private backup files, 18 runtime log files and 27 runtime-root files; these observations apply to this Windows account and machine. The earlier Telegram connection failure and later recovery are point-in-time observations. Earlier performance and memory snapshots retain their original dates and are not load benchmarks.

[Tests](docs/TEST_RESULTS.md) · [Usability](docs/USABILITY_VALIDATION.json) · [Current runtime](docs/CURRENT_RUNTIME_VALIDATION.json) · [PG concurrency](docs/POSTGRES_CONCURRENCY_VALIDATION.json) · [Backup](docs/BACKUP_VALIDATION.json) · [Supervisor](docs/NATIVE_SUPERVISOR_VALIDATION.json) · [Launch](docs/PUBLIC_LAUNCH_VALIDATION.json) · [Operations](docs/OPERATIONS_VALIDATION.md)

## Remaining boundaries

- Complete human Telegram acceptance for file upload, saved JSON report, FixLab, linking and actual Watch delivery. Controlled handler/API tests already cover those paths.
- Execute the entire fresh-machine native bootstrap in a separate environment.
- Source is published at [https://github.com/mitsuhentti/paxveil](https://github.com/mitsuhentti/paxveil); all three [CI jobs](https://github.com/mitsuhentti/paxveil/actions/workflows/ci.yml) passed. No open-source license is currently included.
- Measure capacity before accepting substantial public traffic. No paid hosting or domain has been created.

## Known limits

Uploads are at most 1 MiB and 300 dependencies. Flat manifests can omit transitives; Poetry lock alone can omit root constraints. FixLab uses x86_64 wheel metadata and does not run package builds, uploaded code or application tests. Unknown source coverage remains unknown.

Watch comparisons preserve the last usable OSV baseline through source outages. Telegram delivery is at least once: a crash between remote acknowledgement and database commit can cause a repeat. A phone cannot open the host's localhost; the local bot hides browser links without a suitable public HTTPS web URL and still provides reports in Telegram.

## Resume safely

Read this status and [deployment](docs/DEPLOYMENT.md). Preserve the existing cluster and use the same runtime path. Do not print credentials or Telegram token-bearing URLs. From `outputs/paxveil` in PowerShell 7:

```powershell
.\scripts\stop.ps1 -RuntimeDirectory '..\..\work\runtime'
.\scripts\start.ps1 -Telegram -RuntimeDirectory '..\..\work\runtime'
```

The normal stop/start path was verified. Use the documented force fallback only for the verified project-owned development cluster when ordinary PostgreSQL signaling fails. Daily local backups do not protect against loss of the disk; an owner-controlled private copy elsewhere is needed for that failure.
