# Design and copy review

Delivered update: **12 October 2026**. Browser work took place on 11 and 12 October against the local production application. This update changes presentation and a few UI state handling details; scan data, source provenance and access boundaries retain their existing contracts.

## Visual direction

The interface uses a warm offwhite background, white working surfaces, neutral text and a cobalt accent. Risk states use restrained red, amber and green labels. The light theme is the default; an explicitly selected dark theme remains available and persists in the browser.

The brand is a constructed letter P with a rectangular counter and angled fold. The wordmark export uses outlined SVG paths. The same silhouette is used in the app, favicon, GitHub assets and Telegram profile. Assets include SVG lockups, 16/32-pixel favicon PNGs, an Apple touch icon and 512-pixel Telegram PNG/JPG exports.

The working layout prioritizes project actions and findings. Detailed coverage warnings, dependencies and calculation conditions open on demand. Source availability remains visible. The landing page describes supported files and report contents without invented metrics or sample scan results.

## Copy and implementation

Product slogans and decorative English headings were removed. Interface copy uses short Russian labels. Stable backend messages are translated for display; unknown diagnostics and official advisory descriptions retain their source meaning. Missing CVSS, EPSS, KEV and unresolved update results remain explicit unknown states.

Frontend components and CSS were reformatted into readable source. Existing API payloads, subscriptions, owner checks and history behavior remain in place. The affected fixes are:

- Graph zoom respects the calculated SVG dimensions.
- A pending finding-status response does not reopen a closed modal or overwrite a different selected finding.
- Report and FixLab views are keyed by scan ID when switching between historical and current data.
- A successful zero-finding update result is green; unknown and nonzero results use their corresponding states.
- Mobile table scrolling contains screen-reader-only labels, preventing page-wide horizontal overflow.
- Closed mobile navigation is hidden from accessibility and focus, and the menu control exposes its expanded state.
- Mobile project actions stay aligned; login remains reachable in the landing header.

No dependency or framework upgrade was introduced for the redesign.

## Executed verification

| Check | Result |
| --- | --- |
| Production frontend build | Passed, including TypeScript and page generation |
| Affected Telegram handler/API tests | 24 passed, 1 existing framework warning, 5.17 seconds |
| Ruff and formatting of bot presentation | Passed |
| Source whitespace check | Passed |
| Product copy scan | No old slogan, decorative headings or literal em dash in active frontend, bot templates and revised public guides |
| Real browser | Production UI, existing local QA account and saved Requests report |
| Mobile width | 390 x 844: report document width 375 pixels; dashboard width 390 pixels; no page-wide horizontal overflow |
| Browser error collection | Empty for the final browser tab |

The earlier 122-pass/2-skip full backend result remains dated 11 October. This update reran affected bot coverage and browser checks. Standalone Playwright scenarios were updated to current labels and syntax checked; that runner was not executed in this environment.

The compact browser record is [REDESIGN_VALIDATION.json](REDESIGN_VALIDATION.json). Screenshots retain the browser's original JPEG bytes and use matching file extensions; no screenshot content was edited.

Actual browser actions included:

- Login, project navigation, search and a finding detail with official references.
- Status change and reopening; the original Investigating status was restored.
- Historical report viewing with disabled status editing.
- Graph selection and zoom: SVG width and rendered width both changed from 700 to 840 pixels.
- FixLab through the running API: Minimal Change had insufficient data; the two resolved strategies proposed Requests 2.34.2 and showed 3 known findings before and 0 in the proposal.
- Fire Drill for CVE-2024-35195: saved Requests 2.31.0 matched GHSA-9wx4-h78v-vm56.
- Light/dark switching and keyboard tab navigation with ArrowRight, End and Home.
- Mobile menu navigation, settings and upload form. An unsupported public test filename was rejected in the form.
- Landing and report rendering at desktop and mobile sizes.

These are bounded behavior checks, not a device matrix or a concurrency stress test.

## Local runtime

On resuming on 12 October, the recorded services were stopped and their ports were free. The old manifest was archived without killing another process. The existing PostgreSQL cluster completed WAL recovery and served the saved project.

The final ordinary stop/start completed successfully without the force option. API and web returned HTTP 200, and the worker and bot restarted. The saved report remained available with one dependency and three findings. No database reset or token replacement occurred.

## Telegram profile

The 512-pixel JPG was installed on @PAXVEIL_Bot using the official [setMyProfilePhoto method](https://core.telegram.org/bots/api#setmyprofilephoto). The method returned true, and a profile photo was present afterward. The display name PAXVEIL, short description and description were set and read back successfully. Evidence is in [TELEGRAM_BRAND_VALIDATION.json](TELEGRAM_BRAND_VALIDATION.json).

The profile update does not establish acceptance of every Telegram upload, linking or delivery scenario. The existing live-client checklist remains in [TELEGRAM.md](TELEGRAM.md).

## Screenshots

All screenshots show the running product and public dependencies under a synthetic local QA account.

- [Report](screenshots/redesign-report.jpg), [dark report](screenshots/redesign-report-dark.jpg), [mobile report](screenshots/redesign-report-mobile.jpg).
- [Dashboard](screenshots/redesign-dashboard.jpg), [mobile dashboard](screenshots/redesign-dashboard-mobile.jpg).
- [Landing](screenshots/redesign-landing.jpg), [mobile landing](screenshots/redesign-landing-mobile.jpg).
- [FixLab results](screenshots/redesign-fixlab.jpg), [CVE match](screenshots/redesign-fire.jpg).
- [Mobile settings](screenshots/redesign-settings-mobile.jpg).

Earlier screenshots are retained as dated validation history. The updated source archive contains this redesign. Git history and contributor attribution retain their original records.
