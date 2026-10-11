# Frontend validation

Validated on 2026-10-10 and 2026-10-11 against the real FastAPI / PostgreSQL service. Browser interactions used the in-app browser with Playwright locators; product responses were never mocked.

Final `npm run typecheck` and `npm run build` were repeated successfully on 2026-10-11 against the delivered source. The frontend server was left stopped during the shared startup-script verification.

## Executed checks

- `npm run typecheck`: passed, strict TypeScript.
- `npm run build`: passed, Next.js 16.4 production compilation, TypeScript checking and prerendering.
- Same-origin proxy `/api/health`: returned `ok`, `postgresql`, version `0.1.0`.
- Local account registration and cookie session: passed.
- Empty dashboard: passed, unknown findings represented by an em dash.
- Responsive viewport: 390 × 844; dashboard, report and settings document width was exactly 390 pixels (no page overflow).
- Mobile menu opens and navigates to settings, history and Watch: passed.
- Invalid timezone: real API validation error shown.
- Digest and quiet hours (23:00–07:00, Europe/Moscow): saved and survived page reload.
- Dark and light themes: passed.
- Telegram one-use linking code generation: passed. External Telegram linkage needs a real bot token and client; not claimed here.
- Unsupported upload filename: rejected by the real API while the upload modal remained open.
- Public `requirements.txt` containing `requests==2.31.0`: saved project, asynchronous scan completed; 1 submitted dependency, 3 known findings. Actual scan reported 12.0 seconds. Unpinned transitive dependencies were explicitly warned about.
- Watch enabled, survived reload; disabled through the project switch and remained off after reload.
- Saved scan history and opening immutable historical report: passed; finding status editing is disabled in historical snapshots.
- Browser console error log collection for the mobile session: empty.

Finding status editing initially exposed a stale latest-report projection; the backend was corrected. The final production browser check below confirmed persistence after a complete service restart. Historical status controls remained disabled as expected.

## Final production browser checks — 2026-10-11

These checks were performed through the browser on the running production frontend, using the existing synthetic local account `paxveil_browser_qa` and Requests project `147bccc1-5ff9-46ab-8b88-2dbb8980411f`.

- Changed a finding from Open to Investigating. After a complete service restart and page reload, opening the advisory modal still showed Investigating.
- A report with unavailable CISA KEV enrichment (`kev=null`) showed “Нет данных KEV” in the advisory modal, preserving the distinction between unavailable data and a negative catalogue match.
- Triggered FixLab through the actual “Рассчитать стратегии” UI control and observed all three completed scenario results. Minimal Change reported insufficient data/no eligible update. Balanced and Maximum Coverage proposed `requests` 2.31.0 → 2.34.2; the UI showed known findings 3 → 0 for the resolved metadata simulations. This is a prospective known-vulnerability comparison, not an application compatibility or exploitability guarantee.
- Submitted `CVE-2024-35195` through the actual Fire Drill form. The result confirmed the saved Requests 2.31.0 match and linked the GHSA advisory and official sources.
- Captured the completed real results as `docs/screenshots/fixlab-desktop.jpg` and `docs/screenshots/fire-desktop.jpg`.

No scan durations or other timing measurements were inferred from these browser checks. See the repository's combined validation report for the desktop dependency graph and other integration results.

## Automation limitation

The portable `tests/workspace.spec.ts` and `tests/live-browser.mjs` scenarios cover live upload/report/graph/FixLab/Fire/Watch/settings/deletion. The Windows sandbox rejected Node child-process forks and Edge browser IPC creation. The standalone Playwright runner and CDP script could not execute in this environment. They must be run in CI or an unrestricted local development session. The in-app browser tests above did execute.

## Screenshots

Real screenshots are in `docs/screenshots/`: `dashboard-empty-desktop.jpg`, `dashboard-empty-mobile.jpg`, `settings-mobile.jpg`, `settings-light-mobile.jpg`, `upload-validation-mobile.jpg`, `report-mobile.jpg`, `history-mobile.jpg`, `watch-mobile.jpg`, `advisory-mobile.jpg`, `fixlab-desktop.jpg` and `fire-desktop.jpg`. Linking codes and passwords are excluded from delivered screenshots.

The mobile test-owned account and public-dependency project are stored in the local test database as `paxveil_mobile_qa` / `Mobile Python verification`. Monitoring was disabled after verification.
