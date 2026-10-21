import asyncio
import json
import logging
import os
import time
from datetime import timedelta

import httpx
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from paxveil.config import get_settings
from paxveil.db import (
    Advisory,
    Delivery,
    Dependency,
    Finding,
    FindingState,
    FixScenario,
    Job,
    Notification,
    Package,
    PackageVersion,
    Project,
    Scan,
    SessionLocal,
    SourceSnapshot,
    Subscription,
    User,
    now,
    uid,
)
from paxveil.logging_setup import configure_native_logging
from paxveil.notifications import delivery_time, message_text, schedule_events
from paxveil.resources import cleanup, lock_owner, owner_storage

log = logging.getLogger("paxveil.worker")
settings = get_settings()


class ResourceLimitError(ValueError):
    """An owner can resolve this failure without automatic retries."""


def ingest(db, scan, report):
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert

    def reference(model, fields):
        # Different projects can finish in separate workers at the same time.
        identifier = db.scalar(insert(model).values(**fields).on_conflict_do_nothing().returning(model.id))
        if identifier is None:
            identifier = db.scalar(select(model.id).filter_by(**fields))
        return identifier

    seen_dependencies = set()
    # Shared reference locks use a stable order across differing manifest orders.
    for dep in sorted(report.get("dependencies", []), key=lambda item: (item["name"], item.get("version") or "")):
        if not dep.get("version") or (dep["name"], dep["version"]) in seen_dependencies:
            continue
        seen_dependencies.add((dep["name"], dep["version"]))
        package_id = reference(Package, {"name": dep["name"]})
        version_id = reference(PackageVersion, {"package_id": package_id, "version": dep["version"]})
        db.add(
            Dependency(
                scan_id=scan.id, version_id=version_id, direct=dep.get("direct"), source=dep.get("source", "unknown")
            )
        )
    for finding in sorted(report.get("findings", []), key=lambda item: (item["id"], item["package"], item["version"])):
        fields = {
            "id": finding["id"],
            "aliases": finding.get("aliases", []),
            "data": finding,
            "modified": finding.get("modified"),
            "fetched_at": now(),
        }
        db.execute(
            insert(Advisory)
            .values(**fields)
            .on_conflict_do_update(
                index_elements=[Advisory.id], set_={key: value for key, value in fields.items() if key != "id"}
            )
        )
        advisory = db.get(Advisory, finding["id"])
        db.add(
            Finding(
                scan_id=scan.id,
                advisory_id=advisory.id,
                package=finding["package"],
                version=finding["version"],
                priority=finding.get("priority", 0),
                severity=finding.get("severity", "unknown"),
            )
        )
        state = db.scalar(
            select(FindingState).where(
                FindingState.project_id == scan.project_id,
                FindingState.advisory_id == advisory.id,
                FindingState.package == finding["package"],
            )
        )
        if not state:
            state = FindingState(project_id=scan.project_id, advisory_id=advisory.id, package=finding["package"])
            db.add(state)
            db.flush()
        finding["status"] = state.status
    for source in report.get("sources", []):
        db.add(SourceSnapshot(scan_id=scan.id, source=source.get("name", "unknown"), data=source))


def recover_expired_jobs():
    # Candidate discovery takes no row locks. Each recovery transaction owns
    # one account before touching jobs, matching account deletion and commits.
    with SessionLocal() as db:
        owners = db.scalars(
            select(Job.user_id).where(Job.status == "running", Job.lease_until < now()).distinct().limit(100)
        ).all()
    for owner_id in owners:
        with SessionLocal.begin() as db:
            if not lock_owner(db, owner_id):
                continue
            db.execute(
                update(Job)
                .where(Job.user_id == owner_id, Job.status == "running", Job.lease_until < now())
                .values(status="retry", lease_until=None, run_at=now())
            )


def claim_job():
    recover_expired_jobs()
    with SessionLocal() as db:
        candidates = db.execute(
            select(Job.id, Job.user_id)
            .where(Job.status.in_(["pending", "retry"]), Job.run_at <= now())
            .order_by(Job.created_at, Job.id)
            .limit(100)
        ).all()
    for identifier, owner_id in candidates:
        with SessionLocal.begin() as db:
            # Wait for the short owner transaction rather than skipping every
            # candidate for a busy owner. Revalidate after acquiring its lock.
            if not lock_owner(db, owner_id):
                continue
            job = db.scalar(
                select(Job)
                .where(Job.id == identifier, Job.status.in_(["pending", "retry"]), Job.run_at <= now())
                .with_for_update(skip_locked=True)
            )
            if not job:
                continue
            job.status = "running"
            job.attempts += 1
            job.lease_until = now() + timedelta(minutes=15)
            job.claim_token = uid()
            if job.kind == "scan":
                scan = db.get(Scan, job.scan_id)
                scan.status = "running"
            return job.id, job.claim_token
    return None


def advisory_baseline(db, project_id, scan_id):
    scans = db.scalars(
        select(Scan)
        .where(
            Scan.project_id == project_id,
            Scan.id != scan_id,
            Scan.status.in_(["completed", "partial"]),
            Scan.report.is_not(None),
        )
        .order_by(Scan.created_at.desc())
    )
    for candidate in scans:
        if not isinstance(candidate.report, dict):
            continue
        sources = candidate.report.get("sources", [])
        if candidate.report.get("vulnerability_lookup_complete", True) and any(
            s.get("name") == "OSV" and s.get("status") in {"ok", "cached"} for s in sources
        ):
            return candidate
    return None


async def execute(identifier, claim_token=None):
    from paxveil.core.service import fixlab
    from paxveil.core.service import scan as analyze

    with SessionLocal() as db:
        job = db.get(Job, identifier)
        if not job:
            return
        project = db.get(Project, job.project_id)
        scan = db.get(Scan, job.scan_id)
        if not project or not scan:
            return
        job_kind = job.kind
        arguments = (project.filename, project.content, project.python_version, project.platform)
        base_report = scan.report
    try:
        if job_kind == "scan":
            report = await asyncio.wait_for(
                analyze(arguments[0], arguments[1], python_version=arguments[2], platform=arguments[3], refresh=True),
                timeout=600,
            )
        else:
            report = await asyncio.wait_for(fixlab(base_report), timeout=600)
        report_bytes = len(json.dumps(report).encode())
        if report_bytes > settings.max_report_bytes:
            raise ResourceLimitError("Отчёт превышает лимит хранения. Разделите зависимости на отдельные проекты")
        with SessionLocal.begin() as db:
            # Match enqueue/delete lock order. A deleted owner invalidates work.
            owner_id = db.scalar(select(Job.user_id).where(Job.id == identifier))
            if not owner_id or not lock_owner(db, owner_id):
                return
            job = db.scalar(select(Job).where(Job.id == identifier).with_for_update())
            if not job or job.status != "running" or (claim_token and job.claim_token != claim_token):
                return
            project = db.get(Project, job.project_id)
            scan = db.get(Scan, job.scan_id)
            if owner_storage(db, owner_id) + report_bytes * 2 > settings.max_owner_storage_bytes:
                raise ResourceLimitError("Достигнут лимит хранения. Удалите ненужные проекты")
            if job_kind == "scan":
                prior = advisory_baseline(db, project.id, scan.id)
                ingest(db, scan, report)
                scan.report = report
                scan.finished_at = now()
                scan.status = (
                    "completed"
                    if report.get("completeness") in {"complete", "recorded_versions_checked"}
                    else "partial"
                )
                subscription = db.get(Subscription, project.id)
                # First scan is the baseline. Enabling Watch does not fabricate a new event.
                if prior and subscription and subscription.enabled:
                    schedule_events(db, project, db.get(User, project.user_id), prior.report, report)
            else:
                db.add(FixScenario(job_id=job.id, scan_id=scan.id, report=report))
            job.result = report
            job.status = "succeeded"
            job.lease_until = None
            job.error = None
            db.flush()
            if owner_storage(db, owner_id) > settings.max_owner_storage_bytes:
                raise ResourceLimitError("Достигнут лимит хранения. Удалите ненужные проекты")
        log.info(json.dumps({"event": "job_completed", "job_id": identifier, "kind": job_kind}))
    except Exception as exc:  # noqa: BLE001 -- persist failure state and isolate bounded jobs
        # Avoid logging exception messages: source URLs may include operational credentials.
        log.warning(json.dumps({"event": "job_failed", "job_id": identifier, "type": type(exc).__name__}))
        with SessionLocal.begin() as db:
            owner_id = db.scalar(select(Job.user_id).where(Job.id == identifier))
            if not owner_id or not lock_owner(db, owner_id):
                return
            job = db.scalar(select(Job).where(Job.id == identifier).with_for_update())
            if not job or job.status != "running" or (claim_token and job.claim_token != claim_token):
                return
            job.error = (
                f"{type(exc).__name__}: анализ не завершён; повторите запрос или проверьте доступность источников"
            )
            job.status = "retry" if job.attempts < 3 and not isinstance(exc, ResourceLimitError) else "failed"
            if isinstance(exc, ResourceLimitError):
                job.error = str(exc)
            job.run_at = now() + timedelta(seconds=min(60, 2**job.attempts * 5))
            job.lease_until = None
            if job.kind == "scan":
                scan = db.get(Scan, job.scan_id)
                scan.status = "queued" if job.status == "retry" else "failed"
                scan.error = job.error


def schedule():
    from paxveil.api import enqueue_scan

    with SessionLocal() as db:
        due = db.execute(
            select(Project.id, Project.user_id)
            .join(Subscription)
            .where(Subscription.enabled.is_(True), Subscription.next_check <= now())
            .limit(100)
        ).all()
    for project_id, owner_id in due:
        with SessionLocal.begin() as db:
            if not lock_owner(db, owner_id):
                continue
            subscription = db.scalar(
                select(Subscription)
                .where(
                    Subscription.project_id == project_id,
                    Subscription.enabled.is_(True),
                    Subscription.next_check <= now(),
                )
                .with_for_update(skip_locked=True)
            )
            project = db.get(Project, project_id)
            if not subscription or not project:
                continue
            try:
                enqueue_scan(db, project)
            except HTTPException as exc:
                if exc.status_code != 429:
                    raise
            subscription.next_check = now() + timedelta(seconds=settings.watch_interval_seconds)


async def deliver():
    if not settings.telegram_token:
        return
    with SessionLocal.begin() as db:
        db.execute(
            update(Notification)
            .where(Notification.status == "sending", Notification.lease_until < now())
            .values(status="retry", lease_until=None)
        )
        candidate = db.scalar(
            select(Notification)
            .where(Notification.status.in_(["pending", "retry"]), Notification.run_at <= now())
            .order_by(Notification.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not candidate:
            return
        user = db.get(User, candidate.user_id)
        subscription = db.get(Subscription, candidate.project_id)
        if not user or not user.telegram_id or not subscription or not subscription.enabled:
            candidate.status = "cancelled" if not subscription or not subscription.enabled else "awaiting_link"
            return
        if candidate.category not in user.preferences.get(
            "categories", ["new", "priority", "fix", "exploitation", "status"]
        ) or candidate.payload.get("finding", {}).get("priority", 0) < user.preferences.get("minimum_priority", 0):
            candidate.status = "cancelled"
            return
        due = delivery_time({**user.preferences, "digest": False}, now())
        if due > now() + timedelta(seconds=1):
            candidate.run_at = due
            return
        group = [candidate]
        if user.preferences.get("digest"):
            extras = db.scalars(
                select(Notification)
                .where(
                    Notification.user_id == user.id,
                    Notification.id != candidate.id,
                    Notification.status.in_(["pending", "retry"]),
                    Notification.run_at <= now(),
                )
                .order_by(Notification.created_at)
                .with_for_update(skip_locked=True)
                .limit(4)
            ).all()
            for extra in extras:
                extra_sub = db.get(Subscription, extra.project_id)
                if (
                    not extra_sub
                    or not extra_sub.enabled
                    or extra.category
                    not in user.preferences.get("categories", ["new", "priority", "fix", "exploitation", "status"])
                    or extra.payload.get("finding", {}).get("priority", 0) < user.preferences.get("minimum_priority", 0)
                ):
                    extra.status = "cancelled"
                else:
                    group.append(extra)
        ids = [n.id for n in group]
        claim_tokens = {}
        text = message_text(group, settings.web_url)
        chat = int(user.telegram_id)
        for notification in group:
            notification.status = "sending"
            notification.lease_until = now() + timedelta(minutes=2)
            notification.claim_token = uid()
            claim_tokens[notification.id] = notification.claim_token
            notification.attempts += 1
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage",
                json={
                    "chat_id": chat,
                    "text": text[:4000],
                    "parse_mode": "HTML",
                    "link_preview_options": {"is_disabled": True},
                },
            )
            body = response.json()
            ok = response.is_success and body.get("ok") is True
            permanent = response.status_code in [400, 403]
            retry_after = int(body.get("parameters", {}).get("retry_after", 30))
    except (httpx.HTTPError, ValueError):
        ok, permanent, retry_after = False, False, 30
    with SessionLocal.begin() as db:
        for identifier in ids:
            notification = db.scalar(select(Notification).where(Notification.id == identifier).with_for_update())
            if (
                not notification
                or notification.status != "sending"
                or notification.claim_token != claim_tokens[identifier]
            ):
                continue
            notification.status = (
                "delivered" if ok else "failed" if permanent or notification.attempts >= 5 else "retry"
            )
            notification.lease_until = None
            notification.run_at = now() + timedelta(seconds=retry_after)
            db.add(
                Delivery(
                    notification_id=identifier,
                    status=notification.status,
                    detail="Telegram acknowledged" if ok else "Delivery not acknowledged",
                )
            )


async def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    configure_native_logging("worker")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    log.info(json.dumps({"event": "worker_started", "pid": os.getpid()}))
    maintenance_at = 0.0
    while True:
        try:
            if time.monotonic() >= maintenance_at:
                with SessionLocal.begin() as db:
                    counts = cleanup(db, settings)
                log.info(json.dumps({"event": "retention_cleanup", "removed": counts}))
                maintenance_at = time.monotonic() + 300
            schedule()
            identifier = claim_job()
            if identifier:
                await execute(*identifier)
            await deliver()
        except Exception as exc:  # noqa: BLE001 -- keep the durable worker alive after a failed cycle
            log.error(json.dumps({"event": "worker_cycle_failed", "type": type(exc).__name__}))
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
