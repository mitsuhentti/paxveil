# PAXVEIL Bot

The private-chat bot uses aiogram and Telegram's official HTTPS Bot API. It talks to the same owner-scoped API as the web app and performs no direct database queries. The configured bot is [@PAXVEIL_Bot](https://t.me/PAXVEIL_Bot).

The selected deployment is free local polling on the owner's Windows computer. Other users reach it through Telegram. Only outbound HTTPS is required; no domain, public IP or open router port is needed. The computer, signed-in Windows session, network and services must remain available. This is not an uptime guarantee.

## First use

Send `/start`, then `/example`. The bot sends a small `requirements.txt` containing `requests==2.31.0`. Pressing **Проверить пример** saves a normal project and runs the scanner against current public sources. The example does not contain a prepared result or install the package.

Use `/environment` to choose the Python version and platform for new uploads. Send `requirements.txt`, `poetry.lock` or `uv.lock`; an optional caption names the project. Files are limited to 1 MiB and 300 dependencies. Existing projects retain the environment selected when they were created.

The bot validates file names, binary/empty content, declared size and actual streamed bytes. It polls durable job status for a bounded wait; longer work continues in the backend. Refresh the result or return through `/projects` after the bot restarts.

## Commands and actions

| Command | Action |
| --- | --- |
| `/start` | Main menu |
| `/example` | Public example file and ordinary scan |
| `/projects` | Saved projects and results |
| `/vulnerabilities` | Findings across projects |
| `/fixlab` | Compare update strategies |
| `/fire CVE-2024-35195` | Check a CVE against saved inventory |
| `/watch` | Manage monitoring |
| `/settings` | Notification and environment settings |
| `/environment` | Defaults for new uploads |
| `/privacy` | Data handling and account controls |
| `/export` | Download owner data |
| `/delete_account` | Delete the account after confirmation |

Startup installs the Russian command list. `/link` is advertised when a suitable public HTTPS web URL is configured. Local deployments hide unreachable browser links and provide reports in Telegram. Report links, when available, require browser authentication and contain no session token.

Project actions include rescan, Watch and confirmation-bound deletion. FixLab presents three strategies in Russian, resolves metadata and checks proposals in OSV. It does not establish application compatibility. Source errors, uncertain inventory and incomplete analysis remain visible.

Settings commands are also available:

```text
/timezone Europe/Moscow
/quiet 22:00 08:00
/quiet off
/priority 60
/digest on
/category new off
```

Settings persist through the API. Watch scheduling and notification delivery belong to the worker, not the interactive polling process. Delivery considers category, priority, timezone, quiet hours, digest and unsubscribe changes. A crash after Telegram acknowledgement but before database commit can cause a repeat; exactly-once external delivery is not claimed.

## Data controls

The service stores Telegram identity, uploaded manifests, reports and settings. Package names and versions are sent to public advisory/package sources. It never reads other chats or executes uploaded code. Do not upload secrets.

`/export` returns owner data without password/session hashes or service credentials. Export size is bounded at 40 MiB. Account deletion requires an owner-bound confirmation valid for two minutes and deletes the shared account, including linked web projects. Active-database deletion does not erase messages retained by Telegram or older private backups before rotation. The selected backup policy is normally seven days.

Default quotas include 10 projects, three active jobs, 10 new analyses per rolling hour and 64 MiB of retained owner payloads. [PUBLIC_RESOURCES.md](PUBLIC_RESOURCES.md) records exact limits, cleanup and request windows.

## Configure and run

For a new bot, use the owner's official [@BotFather](https://t.me/BotFather) account. Keep group joining disabled: PAXVEIL processes private chats. The [BotFather guide](https://core.telegram.org/bots/features#botfather) covers account setup and token rotation.

Store the token only in the ignored repository-root `.env` as `TELEGRAM_BOT_TOKEN`. Keep `PAXVEIL_BOT_KEY` as a separate random service secret shared by API and bot. Never paste secrets into chat, screenshots, command arguments or Git.

Start the prepared API/database/worker and one polling process using `scripts/start.ps1 -Telegram`. Use the matching external runtime path for the existing workspace; see [DEPLOYMENT.md](DEPLOYMENT.md). Startup removes an existing webhook without dropping pending updates. Do not run two pollers or an active webhook for the same token.

The API URL is loopback locally and an internal service address in Compose. Remote API credentials require HTTPS. HTTP debug logs must not expose Telegram's token-bearing paths; the configured logging redacts secrets and bounds retained logs.

To link a web account when its HTTPS interface is available, sign in, open **Настройки**, request a code and send `/link CODE`. The code is short-lived and single-use. A project UUID, Telegram ID or callback alone does not authorize access.

## Verification boundary and live acceptance checklist

The profile photo, name and descriptions were applied and read back on 12 October 2026: [brand evidence](TELEGRAM_BRAND_VALIDATION.json). The owner confirmed `/start` in the actual client, then confirmed `/privacy`, `/environment` and `/projects` on 12 October. Polling and installed commands were independently recorded in [launch evidence](PUBLIC_LAUNCH_VALIDATION.json).

On 21 October at 13:54:43 UTC, a fresh official Bot API check passed getMe for @PAXVEIL_Bot, matched all 12 commands in the default and Russian lists, and confirmed no configured webhook. An earlier TelegramNetworkError and unreachable TCP probe recovered before this check. This verifies point-in-time connectivity, not uninterrupted operation or client message delivery. [CURRENT_RUNTIME_VALIDATION.json](CURRENT_RUNTIME_VALIDATION.json) records the failure and recovery separately, alongside current process identities, EFS protection and successful private backup restoration.

The full backend suite passed 178 tests on 21 October. Bot tests feed controlled updates through aiogram; component tests use the real FastAPI routes, a temporary database and durable worker with controlled source responses. They check routing, downloads, progress, reports, ownership, callbacks, linking, settings, export, deletion and errors. They do not establish actual Telegram-client file delivery or external Watch notifications.

Complete the remaining checks in a real private chat:

1. Run `/example`, start its scan and download the saved JSON report.
2. Upload your own supported public fixture; verify environment, queue/progress and recovery through `/projects`.
3. Run FixLab and inspect a completed strategy; check a known CVE against the saved project.
4. Enable Watch, save settings and verify an actual notification when a qualifying change occurs. Controlled notification tests remain separate evidence.
5. Where a reachable web deployment exists, link once and verify that reusing the code is rejected.
6. Export data, then delete only a disposable test project/account after checking the confirmation scope.

[TEST_RESULTS.md](TEST_RESULTS.md) distinguishes automated, live-source and human checks. The native supervisor passed all 19 checks again on 21 October: [evidence](NATIVE_SUPERVISOR_VALIDATION.json). The 20 same-day [browser checks](USABILITY_VALIDATION.json) covered a genuine sample scan, FixLab recovery, historical scan links, filters, settings drafts/errors and mobile focus/navigation; they do not substitute for the Telegram-client checklist. [OPERATIONS_VALIDATION.md](OPERATIONS_VALIDATION.md) records native operation. No cloud hosting or public browser deployment has been created.
