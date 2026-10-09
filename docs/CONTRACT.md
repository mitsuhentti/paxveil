# PAXVEIL implementation contract

API on localhost:8000, Next.js on localhost:3000 proxies `/api/*` to backend. Cookie sessions (HttpOnly) in browser; Bearer sessions in Telegram. All data access is owner scoped. No seeded production reports.

## JSON report

`{dependencies:[{name,version,direct,source,marker?,status}], findings:[{id,aliases,package,version,summary,severity,cvss,epss,epss_date,kev,priority,priority_reasons,affected,fixed_versions,references,published,modified,status}], graph:{nodes:[{id,name,version,direct}],edges:[{source,target}]}, warnings:[string], sources:[{name,status,fetched_at,error?}], stats:{dependencies,findings,duration_seconds}, completeness: string, environment:{python_version,platform}}`.

Use package==version as graph IDs. Null when unknown. Severity is critical/high/medium/low/unknown. Priority integer 0..100. Core scan must return partial report when enrichment fails and never treat OSV failure as a clean result. `scan(filename: str, content: bytes, python_version='3.11', platform='linux', refresh=False) -> dict` in `paxveil.core.service`. `fire(cve: str, reports: list[dict]) -> dict`; `fixlab(report: dict) -> dict` are async functions in same module, importing supporting modules as needed. Reports passed to fire include project_id and project_name. FixLab returns `{strategies:[{name,updates,before,after,conflicts,uncertainties,graph_changes,reason,status}],limitations:[...]}`.

## API routes

- POST /api/auth/register and /api/auth/login {username,password}; GET /api/auth/me; POST /api/auth/logout. User JSON {id,username,telegram_id?}.
- GET /api/projects -> array of {id,name,created_at,watch,latest_scan:{id,status,created_at,report?}|null}
- POST /api/projects multipart name, file, python_version (default 3.11), platform (linux/windows/darwin) -> project object, latest_scan queued.
- GET /api/projects/{id} -> project object with latest_scan.report.
- DELETE /api/projects/{id}; POST /api/projects/{id}/scan -> {id:job_id,scan_id,status}.
- GET /api/projects/{id}/scans -> scans array; GET /api/scans/{id} -> {id,status,report,error?,created_at}.
- GET /api/jobs/{id} -> {id,status,kind,result,error,attempts}.
- POST /api/scans/{id}/fixlab -> {id:job_id,status}; worker result = FixLab report.
- POST /api/fire {cve} -> {cve,status,advisories,matches,limitations}, matches contain {project_id,project_name,package,version,status,advisory_id,path,fixed_versions,references}.
- GET /api/settings -> {telegram_id,timezone,quiet_start,quiet_end,minimum_priority,digest,categories}; PUT /api/settings same editable fields.
- PUT /api/projects/{id}/watch {enabled:boolean} -> {enabled}; GET /api/notifications -> array.
- POST /api/auth/telegram/link -> {code,expires_at} web session required.
- POST /api/bot/identity {telegram_id} with X-Bot-Key -> {token,user}, Bot uses token with Authorization: Bearer for all ordinary API calls.
- POST /api/bot/link {telegram_id,code} with X-Bot-Key -> {token,user}; merges Telegram-owned projects into web owner, consumes one-use code.
- GET /api/health -> {status,database,version}.

## Ownership of files

Root: DB models/migrations, API/auth, durable worker/scheduler/notifications, infrastructure/docs/integration QA.
Core agent: backend/paxveil/core/*, backend/tests/test_core*, backend requirements file (coordinate dependencies).
Frontend agent: frontend/*, SVG brand assets, frontend tests and npm dependencies.
Telegram agent: backend/paxveil/bot/*, backend/tests/test_bot*, docs/TELEGRAM.md. Bot calls API, never reads DB directly.

Python env is work/runtime/venv at task workspace (outside source repository). Python 3.11 installed. PostgreSQL binaries C:/Program Files/PostgreSQL/18/bin. Use absolute paths as necessary.
