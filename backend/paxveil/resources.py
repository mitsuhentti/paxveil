"""Database-backed public limits and bounded owner data retention."""

import hashlib
import json
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import Text, cast, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from paxveil.db import (
    FindingState,
    FixScenario,
    Job,
    LinkCode,
    Notification,
    Project,
    RequestLimit,
    Scan,
    Session,
    SourceSnapshot,
    StatusHistory,
    User,
    now,
)

ACTIVE_JOBS = ("pending", "running", "retry")
TERMINAL_JOBS = ("succeeded", "failed")


def request_window(
    db, namespace: str, identity: str, maximum: int, seconds: int = 60, *, at: datetime | None = None
) -> tuple[bool, int]:
    """One atomic upsert; rejected requests cannot increase the counter forever."""
    at = at or now()
    epoch = int(at.timestamp())
    window = epoch // seconds
    retry_after = seconds - epoch % seconds
    key = hashlib.sha256(f"{namespace}:{identity}:{window}".encode()).hexdigest()
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    statement = insert(RequestLimit).values(key_hash=key, count=1, expires_at=at + timedelta(seconds=retry_after))
    statement = statement.on_conflict_do_update(
        index_elements=[RequestLimit.key_hash],
        set_={"count": RequestLimit.count + 1},
        where=RequestLimit.count < maximum,
    ).returning(RequestLimit.count)
    accepted = db.scalar(statement) is not None
    return accepted, retry_after


def limit_error(code: str, message: str, retry_after: int = 3600):
    raise HTTPException(429, {"code": code, "message": message}, headers={"Retry-After": str(retry_after)})


def owner_storage(db, user_id: str) -> int:
    """Count manifest and report payloads, including persisted report copies."""
    manifests = db.scalar(
        select(func.coalesce(func.sum(func.length(Project.content)), 0)).where(Project.user_id == user_id)
    )
    reports = db.scalar(
        select(func.coalesce(func.sum(func.length(cast(Scan.report, Text))), 0))
        .join(Project)
        .where(Project.user_id == user_id)
    )
    results = db.scalar(
        select(func.coalesce(func.sum(func.length(cast(Job.result, Text))), 0)).where(Job.user_id == user_id)
    )
    fixes = db.scalar(
        select(func.coalesce(func.sum(func.length(cast(FixScenario.report, Text))), 0))
        .join(Job, FixScenario.job_id == Job.id)
        .where(Job.user_id == user_id)
    )
    notifications = db.scalar(
        select(func.coalesce(func.sum(func.length(cast(Notification.payload, Text))), 0)).where(
            Notification.user_id == user_id
        )
    )
    snapshots = db.scalar(
        select(func.coalesce(func.sum(func.length(cast(SourceSnapshot.data, Text))), 0))
        .join(Scan, SourceSnapshot.scan_id == Scan.id)
        .join(Project, Scan.project_id == Project.id)
        .where(Project.user_id == user_id)
    )
    states = db.execute(
        select(
            FindingState.id,
            FindingState.project_id,
            FindingState.advisory_id,
            FindingState.package,
            FindingState.status,
        )
        .join(Project, FindingState.project_id == Project.id)
        .where(Project.user_id == user_id)
        .execution_options(yield_per=1000)
    ).mappings()
    state_bytes = serialized_row_bytes(states)
    history = db.execute(
        select(
            StatusHistory.id,
            StatusHistory.state_id,
            StatusHistory.old_status,
            StatusHistory.new_status,
            StatusHistory.changed_at,
        )
        .join(FindingState, StatusHistory.state_id == FindingState.id)
        .join(Project, FindingState.project_id == Project.id)
        .where(Project.user_id == user_id)
        .execution_options(yield_per=1000)
    ).mappings()
    history_bytes = serialized_row_bytes(history)
    return int(manifests + reports + results + fixes + notifications + snapshots + state_bytes + history_bytes)


def serialized_row_bytes(rows) -> int:
    """Count canonical compact JSON bytes without materializing the whole history."""
    total = 0
    for row in rows:
        fields = {key: value.isoformat() if isinstance(value, datetime) else value for key, value in row.items()}
        total += len(json.dumps(fields, ensure_ascii=True, separators=(",", ":")).encode())
    return total


def prune_status_history(db, project_id: str, retained: int) -> int:
    # The caller owns the account lock. Timestamp ties are resolved by the
    # increasing row ID so the newest transition is always retained.
    stale = (
        select(StatusHistory.id)
        .join(FindingState, StatusHistory.state_id == FindingState.id)
        .where(FindingState.project_id == project_id)
        .order_by(StatusHistory.changed_at.desc(), StatusHistory.id.desc())
        .offset(retained)
    )
    return db.execute(
        delete(StatusHistory).where(StatusHistory.id.in_(stale)).execution_options(synchronize_session="fetch")
    ).rowcount


def lock_owner(db, user_id):
    return db.scalar(select(User).where(User.id == user_id).with_for_update())


def check_job_budget(db, user_id, settings):
    # Caller holds the owner lock until it commits the job insertion.
    active = db.scalar(select(func.count()).select_from(Job).where(Job.user_id == user_id, Job.status.in_(ACTIVE_JOBS)))
    if active >= settings.max_active_jobs_per_user:
        limit_error("active_job_limit", "Уже выполняются задачи. Дождитесь их завершения", 60)
    recent = db.scalar(
        select(func.count())
        .select_from(Job)
        .where(Job.user_id == user_id, Job.created_at >= now() - timedelta(hours=1))
    )
    if recent >= settings.max_analysis_jobs_per_hour:
        limit_error("analysis_limit", "Достигнут лимит анализов за час. Повторите позже")
    if owner_storage(db, user_id) >= settings.max_owner_storage_bytes:
        limit_error("storage_limit", "Достигнут лимит хранения. Удалите ненужные проекты")


def cleanup(db, settings, *, at=None) -> dict[str, int]:
    """Retain active work and the latest usable Watch baseline while pruning history."""
    at = at or now()
    counts = {
        "request_limits": db.execute(
            delete(RequestLimit).where(RequestLimit.expires_at <= at).execution_options(synchronize_session="fetch")
        ).rowcount
    }
    # Bounded batches rotate by their last cleanup date. Lock owners first so
    # cleanup cannot invert the enqueue/delete/session-refresh lock order.
    owners = db.scalars(
        select(User)
        .order_by(User.last_maintenance_at.asc().nulls_first(), User.id)
        .with_for_update(skip_locked=True)
        .limit(100)
    ).all()
    owner_ids = [owner.id for owner in owners]
    for owner in owners:
        owner.last_maintenance_at = at
    for model in (Session, LinkCode):
        counts[model.__tablename__] = db.execute(
            delete(model)
            .where(model.user_id.in_(owner_ids), model.expires_at <= at)
            .execution_options(synchronize_session="fetch")
        ).rowcount
    counts["notifications"] = db.execute(
        delete(Notification)
        .where(
            Notification.status != "sending",
            Notification.user_id.in_(owner_ids),
            Notification.created_at < at - timedelta(days=settings.notification_retention_days),
        )
        .execution_options(synchronize_session="fetch")
    ).rowcount
    counts["jobs"] = db.execute(
        delete(Job)
        .where(
            Job.user_id.in_(owner_ids),
            Job.status.in_(TERMINAL_JOBS),
            Job.created_at < at - timedelta(days=settings.terminal_job_retention_days),
        )
        .execution_options(synchronize_session="fetch")
    ).rowcount
    counts["scans"] = 0
    counts["finding_status_history"] = 0
    for project_id in db.scalars(select(Project.id).where(Project.user_id.in_(owner_ids))).all():
        db.execute(select(Project.id).where(Project.id == project_id).with_for_update()).scalar_one_or_none()
        counts["finding_status_history"] += prune_status_history(
            db, project_id, settings.retained_status_changes_per_project
        )
        scans = db.scalars(
            select(Scan)
            .where(Scan.project_id == project_id, Scan.status.in_(["completed", "partial", "failed"]))
            .order_by(Scan.created_at.desc(), Scan.id)
        ).all()
        retained = {scan.id for scan in scans[: settings.retained_scans_per_project]}
        # Long source outages must not erase the last complete OSV comparison.
        for scan in scans:
            report = scan.report or {}
            if report.get("vulnerability_lookup_complete", True) and any(
                source.get("name") == "OSV" and source.get("status") in {"ok", "cached"}
                for source in report.get("sources", [])
            ):
                retained.add(scan.id)
                break
        active_scans = set(
            db.scalars(select(Job.scan_id).where(Job.project_id == project_id, Job.status.in_(ACTIVE_JOBS)))
        )
        obsolete = [scan.id for scan in scans if scan.id not in retained and scan.id not in active_scans]
        if obsolete:
            counts["scans"] += db.execute(delete(Scan).where(Scan.id.in_(obsolete))).rowcount
    return counts
