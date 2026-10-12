# PAXVEIL Bot

The private-chat interface uses aiogram 3.31 and Telegram's official HTTPS Bot API. It calls the same PAXVEIL HTTP API as the browser. Project content, settings, scan history and subscriptions are stored by the backend; the bot has no database credentials or direct database access.

On 12 October 2026 the redesigned profile photo, display name **PAXVEIL**, short description and description were applied to @PAXVEIL_Bot and read back successfully. [TELEGRAM_BRAND_VALIDATION.json](TELEGRAM_BRAND_VALIDATION.json) records the API checks. The uploaded JPG is [telegram-icon.jpg](../frontend/public/telegram-icon.jpg); SVG and PNG exports are also available. Product labels use Russian status, severity and strategy names while preserving unknown diagnostics.

## Create the bot in your Telegram account

These steps require the owner's Telegram account. The owner supplied a token through the local ignored `.env`; on 2026-10-11 the official API identified the configured bot as **[@PAXVEIL_Bot](https://t.me/PAXVEIL_Bot)** and polling started successfully. The owner then confirmed that `/start` displayed the menu in their Telegram client; bot logs recorded two handled updates. No external account was created by the development agent. The following instructions also apply to a fresh installation.

1. Open the official [@BotFather](https://t.me/BotFather), verify the username, and send `/newbot`.
2. Use the display name **PAXVEIL**. Pick an available username ending in `bot`; the product name does not imply that a particular Telegram username is available.
3. Copy the resulting token directly into the local repository-root `.env`, in `TELEGRAM_BOT_TOKEN`. Do not put it in chat, a screenshot, source files, command-line arguments or Git.
4. Use `/setjoingroups` → Disable. PAXVEIL only processes private chats. Keep `/setprivacy` enabled; inline mode, Guest Mode, Bot Management Mode and Business integration are unnecessary.
5. Use `/setdescription`: `Проверяйте Python-зависимости, сравнивайте обновления в FixLab и получайте уведомления PAXVEIL Watch.`
6. Use `/setabouttext`: `Проверка Python-зависимостей и уведомления об уязвимостях.`

The polling process configures the following Russian command list at startup. You can also set it through BotFather `/setcommands`:

```text
start - Главное меню PAXVEIL
projects - Мои проекты
vulnerabilities - Уязвимости проектов
fixlab - Сравнить варианты обновления
fire - Проверить CVE во всех проектах
watch - Управление мониторингом
settings - Уведомления и связь с веб-аккаунтом
link - Связать Telegram одноразовым кодом
```

The official [BotFather guide](https://core.telegram.org/bots/features#botfather) describes creation, command lists and privacy settings. If a token is exposed, rotate it in BotFather and replace the local value before restarting. Treat `PAXVEIL_BOT_KEY` separately: it authorizes the bot service to obtain owner-scoped sessions and must be private too.

## Local configuration and launch

API, worker, database and browser setup are described in the repository README. The API and worker must already be running before starting the bot. In a fresh checkout, create `.env` from `.env.example` only if `.env` does not already exist. Preserve the backend's existing configuration.

Configure these repository-root `.env` entries locally:

```dotenv
TELEGRAM_BOT_TOKEN=
PAXVEIL_BOT_KEY=
PAXVEIL_API_URL=http://localhost:8000
PAXVEIL_WEB_URL=http://localhost:3000
```

Fill the token from BotFather. Use the same cryptographically random `PAXVEIL_BOT_KEY` in API and bot configuration (at least 32 random bytes). An existing setup may already have generated this value. Never use the Telegram token as the API bot key. `.env` is ignored by Git. The application reads the repository-root file; environment variables take precedence.

From the repository root with its Python environment active:

```powershell
Set-Location backend
python -m paxveil.bot
```

Only start one polling instance for a token. `Ctrl+C` stops it. Startup removes an existing webhook without dropping pending updates and installs the command list; these actions happen only when the operator runs the configured bot. Missing credentials cause a clear local error before any Telegram request. The process never prints either secret. Do not run production with debug HTTP logging, which could expose Telegram's token-bearing request paths.

Local polling needs outbound HTTPS to `api.telegram.org`, plus connectivity to `PAXVEIL_API_URL`. It does not need an incoming port or public webhook. A deployed worker also needs this HTTPS access to send Watch notifications. When using containers, the bot API address is the internal API service, for example `http://api:8000`; the web URL must remain the address the human can open. Use HTTPS for a remote API. The bot rejects a remote HTTP API URL before transmitting session credentials.

`localhost` links point to the device that opens them. A phone cannot open the computer's localhost report. In local development open the displayed link on that computer and sign in to the linked web account. A public HTTPS URL requires a separately approved deployment; none is published automatically. Report links never contain authentication tokens.

## User flow

Send `/start` in a private chat. The seven working menu actions are file analysis, projects, vulnerabilities, FixLab, Fire Drill, Watch and settings.

In the browser, Watch is labeled **Мониторинг** and Fire Drill is **Проверка CVE**. Project tabs are **Отчёт**, **Зависимости**, **Обновления** and **История**. Web uploads start with **Новый проект**, followed by **Создать проект и проверить**. The updated flat P identity and responsive light/dark interface are documented in [design review](DESIGN_REVIEW.md).

Send `requirements.txt`, `poetry.lock` or `uv.lock`, with an optional caption for the project name. The bot rejects other filenames, empty/binary files and files over **1 MiB**. It also limits the streaming download even when metadata understates the size. The backend validates the actual format. Uploading saves the project and queues its scan; no dependency code is executed. Telegram uploads currently target Python 3.11/Linux. For a different target environment, upload through the web interface.

The bot polls persisted scan/job status for up to two minutes and shows queue/running/retry transitions. A longer job continues in the durable backend queue; the message supplies a refresh button. `/projects` always restores access to saved results after the bot restarts. Reports show source limitations and uncertainty, include a full JSON document, and provide a login-gated browser link. Empty findings are never described as proof that a project is secure.

Open a project to scan again, enable/disable Watch or request deletion. Deletion requires a user-bound, single-use confirmation that expires after two minutes. FixLab asks for a project and one of Minimal Change, Balanced or Maximum Coverage, waits for the API job and summarizes that strategy. It models changes and makes no promise of application compatibility.

For Fire Drill, use `/fire CVE-2024-35195` or another existing CVE. This queries the backend sources and compares the CVE with the owner's persisted reports. Source failures and limitations remain visible; a vulnerable package version is not proof of exploitability in the application.

## Link a web account

1. Register/sign in to PAXVEIL in the browser.
2. Open Settings (**Настройки**) and press **Получить код** to request the Telegram link code.
3. In your private PAXVEIL Bot chat, send `/link CODE`.
4. The API consumes the short-lived code and merges existing Telegram-owned projects into the authenticated web owner. Bot replies do not repeat the code; the bot attempts to remove the command message from the chat.
5. `/projects` and web refresh now show the same owner-scoped data. Opening a report URL still requires browser login.

Link codes are generated by the authenticated web API. Knowing a Telegram ID, project UUID, report URL or callback payload does not authorize access. Never forward a live link code to another person. The bot exchanges its service key at `/api/bot/identity` or `/api/bot/link`, then uses an expiring Bearer session for ordinary API routes. The API enforces ownership on every object.

## Notification settings

Settings are persistent API data shared with the browser. Commands work directly and the settings menu shows their current values:

```text
/timezone Europe/Moscow
/quiet 22:00 08:00
/quiet off
/priority 60
/digest on
/digest off
/category new off
/category fix on
```

Timezones are IANA names; quiet hours use local 24-hour time and may span midnight. Priority is 0–100. Categories are `new`, `priority`, `fix`, `exploitation`, `status`. Enabled Watch subscriptions are shown first in the monitoring menu. The backend scheduler/delivery outbox owns notification comparisons, deduplication, retries, quiet hours and daily digests. The bot process owns interactive polling only.

Stopping the local worker stops scheduled checks/delivery. A continuously running server is needed for around-the-clock monitoring. Restarting the bot does not erase projects or subscriptions. Temporary in-memory deletion confirmations and progress waits expire on restart; the user can reopen their project.

## Verification boundary and live acceptance checklist

Automated handler tests use `Dispatcher.feed_raw_update` with controlled Telegram and HTTP transports. Their advisory/package records exist only in test fixtures. They make no external Telegram calls. They verify menu routing, uploads and streaming limits, status polling, HTML escaping, report delivery, callback validation, API ownership denial, Watch updates, selected FixLab strategies, Fire Drill routing, settings validation, session renewal, one-use link behavior, confirmation-bound deletion and sanitized errors.

An additional integration test sends synthetic Telegram updates through the FastAPI ASGI routes, temporary SQLite database and durable worker, then enables Watch and links a web account through a single-use API code. The vulnerability report uses a controlled core fixture. This test checks component compatibility; it does not query live advisories or deliver messages through Telegram.

Run these tests from `backend`:

```powershell
python -m pytest tests/test_bot.py tests/test_bot_api.py -q
python -m ruff check paxveil/bot tests/test_bot.py tests/test_bot_api.py
```

**Token validation, polling and `/start` menu display were confirmed on 2026-10-11 for [@PAXVEIL_Bot](https://t.me/PAXVEIL_Bot).** Bot logs recorded two handled updates before the final restart; polling was verified again after initialization and the native stop/start check. File uploads, reports, linking and Watch delivery still require human acceptance in Telegram. Tests with synthetic updates cover the broader handler behavior. The locally saved token is not included in the repository or this document. See [operational validation](OPERATIONS_VALIDATION.md) for the native startup/shutdown evidence.

Continue this checklist in the owner's private bot chat:

- `/start` and menu display are confirmed. Continue with every menu button and return to the main menu.
- Link a web account; reuse its code and verify rejection.
- Upload a supported dependency file, inspect queued/running/completed status, save/report behavior and source completeness.
- Download its JSON report; open the web link on a reachable device and confirm browser login is required.
- Scan again, inspect vulnerabilities, and run each FixLab strategy.
- Run a CVE Fire Drill, checking a match against the official advisory and a nonmatching project.
- Enable Watch, change priority/timezone/quiet hours/digest/categories, restart bot and verify those settings remain.
- Exercise notification delivery and a temporary failure with the separate controlled notification fixtures; verify retries, no duplicates, quiet hours, unsubscribe and owner isolation.
- Disable Watch, delete a test project only after confirmation, and verify it disappears in the browser.

Relevant implementation references: [aiogram dispatcher](https://docs.aiogram.dev/en/latest/dispatcher/dispatcher.html), [file downloads](https://docs.aiogram.dev/en/latest/api/download_file.html), [file uploads](https://docs.aiogram.dev/en/latest/api/upload_file.html), and [Telegram Bot API](https://core.telegram.org/bots/api).
