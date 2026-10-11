import hashlib
import html
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from paxveil.db import Notification, now


def event_changes(previous: dict, current: dict):
    if previous.get("vulnerability_lookup_complete") is False or current.get("vulnerability_lookup_complete") is False:
        return
    old = previous.get("findings", [])
    for finding in current.get("findings", []):
        identities = {finding["id"], *finding.get("aliases", [])}
        before = next((f for f in old if f["package"] == finding["package"] and f["version"] == finding["version"] and identities.intersection({f["id"], *f.get("aliases", [])})), None)
        if before is None:
            yield "new", finding
            continue
        enrichment_lost = any((before.get(key) is None) != (finding.get(key) is None) for key in ["epss", "kev", "cvss"])
        if finding.get("priority") != before.get("priority") and not enrichment_lost:
            yield "priority", finding
        if set(finding.get("fixed_versions", [])) - set(before.get("fixed_versions", [])):
            yield "fix", finding
        if finding.get("kev") is True and before.get("kev") is False:
            yield "exploitation", finding
        if finding.get("status", "open") != before.get("status", "open"):
            yield "status", finding


def schedule_events(db, project, user, previous, current):
    prefs = user.preferences
    for category, finding in event_changes(previous, current):
        if category not in prefs.get("categories", ["new", "priority", "fix", "exploitation", "status"]):
            continue
        if finding.get("priority", 0) < prefs.get("minimum_priority", 0):
            continue
        identities = {finding["id"], *finding.get("aliases", [])}
        canonical = min((value for value in identities if value.startswith("CVE-")), default=min(identities))
        fingerprint = json.dumps({"project": project.id, "id": canonical, "package": finding["package"], "version": finding["version"], "category": category, "modified": finding.get("modified"), "priority": finding.get("priority"), "fixed": finding.get("fixed_versions"), "kev": finding.get("kev"), "status": finding.get("status"), "status_changed_at": finding.get("status_changed_at")}, sort_keys=True)
        key = hashlib.sha256(fingerprint.encode()).hexdigest()
        if db.scalar(select(Notification.id).where(Notification.event_key == key)):
            continue
        db.add(Notification(user_id=user.id, project_id=project.id, event_key=key, category=category, payload={"project_name": project.name, "finding": finding}, run_at=delivery_time(prefs, now())))


def delivery_time(preferences: dict, instant: datetime):
    local = instant.astimezone(ZoneInfo(preferences.get("timezone", "Europe/Moscow")))
    if preferences.get("digest"):
        target = local.replace(hour=9, minute=0, second=0, microsecond=0)
        if target <= local:
            target += timedelta(days=1)
        local = target
    start, end = preferences.get("quiet_start"), preferences.get("quiet_end")
    if start and end:
        hour, minute = map(int, end.split(":"))
        clock = local.strftime("%H:%M")
        quiet = (start <= clock < end) if start < end else (clock >= start or clock < end)
        if quiet:
            target = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= local:
                target += timedelta(days=1)
            local = target
    return local.astimezone(instant.tzinfo)


def message_text(notifications: list, web_url: str):
    lines = ["<b>PAXVEIL Watch</b>"]
    for notification in notifications:
        f = notification.payload["finding"]
        lines.append(f"{html.escape(notification.payload['project_name'])}: {html.escape(f['package'])} {html.escape(f['version'])}\n{html.escape(f['id'])} · приоритет {f.get('priority', 0)}/100 · {html.escape(notification.category)}")
    lines.append("Совпадение версии с advisory не подтверждает эксплуатацию в приложении.")
    project_id = notifications[0].project_id
    lines.append(f'<a href="{html.escape(web_url, quote=True)}/app/projects/{project_id}">Открыть отчёт</a>')
    return "\n\n".join(lines)
