# PAXVEIL web

Next.js 16 / React 19 / strict TypeScript, with Radix Dialog for accessible modal interactions. The visual identity uses a geometric dependency-node mark, graphite surfaces and a restrained cyan signal colour. No external font or image service is required.

```powershell
npm ci
npm run dev
```

Open http://127.0.0.1:3000. Start the backend on port 8000 first. All `/api/*` requests are same-origin and proxied by Next.js; sessions use HttpOnly cookies managed by the API. `API_INTERNAL_URL` (or `PAXVEIL_API_URL`) configures the proxy upstream at build time. The container build defaults to `http://api:8000`.

In a Windows sandbox that denies child-process forks, `npm run dev:in-process` starts the same app without the CLI process supervisor. TypeScript 6 is pinned because it offers the compiler API required for a worker-thread build; the production build still performs full strict type checking.

```powershell
npm run typecheck
npm run build
npm run test:e2e
```

The browser tests use the real running API and create isolated test-owned projects from public dependency names. They do not stub product data. Install Playwright Chromium with `npx playwright install chromium`, or set `PLAYWRIGHT_CHANNEL=msedge` to use installed Edge. Test artefacts and screenshots are in `test-results/`.

`npm run test:e2e:cdp` runs the same acceptance scenario in-process against an explicitly started isolated browser at `PLAYWRIGHT_CDP_URL` (default `http://127.0.0.1:9223`). The current Windows sandbox denies browser IPC process creation, so the standalone scripts were not executed here; the application was tested through the browser automation instead. See `../docs/FRONTEND_VALIDATION.md` for observed results and screenshots.

Routes: `/` (landing), `/login`, `/app` (projects), `/app/projects/{uuid}?tab=report|graph|fixlab|history`, `/app/watch`, `/app/fire`, `/app/history`, `/app/settings`.

Light/dark theme is a browser preference. Authentication tokens are never stored in localStorage or embedded in URLs. External advisory links accept HTTP(S) only. API errors, incomplete scans and unavailable metadata are shown explicitly.
