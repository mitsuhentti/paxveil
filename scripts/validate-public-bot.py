"""Read-only checks of the configured public bot and local deployment.

No Telegram messages are sent, user updates are not consumed, and no private
account or uploaded manifest data enters the evidence file.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
from aiogram import Bot
from sqlalchemy import text

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))
from paxveil.config import get_settings
from paxveil.db import SessionLocal


def encrypted(path: Path) -> bool:
    return bool(getattr(path.stat(), "st_file_attributes", 0) & 0x4000)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    settings = get_settings()
    with httpx.Client(timeout=10, trust_env=False) as client:
        api_health = client.get("http://127.0.0.1:8000/api/health")
        api_health.raise_for_status()
        web = client.get("http://127.0.0.1:3000/")
        web.raise_for_status()
    with SessionLocal() as db:
        migration = db.scalar(text("SELECT version_num FROM alembic_version"))
        active_jobs = db.scalar(text("SELECT COUNT(*) FROM jobs WHERE status IN ('pending','running','retry')"))
    async with Bot(settings.telegram_token) as bot:
        identity = await bot.get_me()
        commands = await bot.get_my_commands()
        russian = await bot.get_my_commands(language_code="ru")
        webhook = await bot.get_webhook_info()
    required = {"start", "projects", "fixlab", "fire", "watch", "environment", "privacy", "export", "delete_account"}
    command_names = {item.command for item in commands}
    russian_names = {item.command for item in russian}
    assert required <= command_names and required <= russian_names
    assert not webhook.url, "Polling requires no active webhook"
    data_files = [path for path in (runtime / "pgdata").rglob("*") if path.is_file()]
    backup_files = [path for path in (runtime / "backups").glob("*") if path.suffix in {".dump", ".json"}]
    evidence = {
        "verified_at": datetime.now(UTC).isoformat(),
        "hosting": "Owner's Windows computer; no hosting subscription",
        "availability": "Computer powered on, connected and Windows signed in; manual sleep and shutdown stop service",
        "scope": "Live read-only HTTP, PostgreSQL and official Telegram Bot API; not a Telegram client upload acceptance check",
        "api_http_status": api_health.status_code,
        "web_http_status": web.status_code,
        "database_revision": migration,
        "active_jobs_observed": active_jobs,
        "telegram": {"username": identity.username, "get_me": "passed", "commands": sorted(command_names), "russian_commands": sorted(russian_names), "webhook_configured": False},
        "native": {"supervisor_state_present": (runtime / "supervisor.json").is_file(), "supervision_enabled": (runtime / "supervisor.enabled").is_file(), "daily_backup_checkpoint_present": (runtime / "backup-last-success.txt").is_file()},
        "at_rest": {"method": "Windows EFS; user certificate key stored separately in Windows", "database_files": len(data_files), "all_database_files_encrypted": bool(data_files) and all(encrypted(path) for path in data_files), "private_backup_files": len(backup_files), "all_private_backup_files_encrypted": bool(backup_files) and all(encrypted(path) for path in backup_files), "secret_file_encrypted": encrypted(REPO / ".env"), "log_directory_encrypted": encrypted(runtime / "logs")},
        "remaining": ["Real Telegram upload/report/FixLab/Watch acceptance by a human; controlled handler/API checks are separate", "Windows reboot/sign-in was not simulated as an actual reboot", "No uptime SLA or public traffic capacity benchmark"],
    }
    assert all(evidence["at_rest"][key] for key in ("all_database_files_encrypted", "all_private_backup_files_encrypted", "secret_file_encrypted", "log_directory_encrypted"))
    (REPO / "docs" / "PUBLIC_LAUNCH_VALIDATION.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    try:
        asyncio.run(main())
    except Exception as exc:  # noqa: BLE001 -- token-bearing SDK errors must not reach output
        print(json.dumps({"result": "failed", "error_type": type(exc).__name__}), file=sys.stderr)
        raise SystemExit(1) from None
