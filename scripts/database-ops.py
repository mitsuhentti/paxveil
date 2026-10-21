"""Private PostgreSQL backups and disposable restore/concurrency verification.

Use the project's Python environment. Connection credentials come from the local
environment or .env and are never placed in subprocess arguments or evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))
from paxveil.config import get_settings


def connection_options(database=None):
    url = make_url(get_settings().database_url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("These operations require PostgreSQL")
    return {
        "host": url.host or "127.0.0.1",
        "port": url.port or 5432,
        "user": url.username,
        "password": url.password,
        "dbname": database or url.database,
        "connect_timeout": 10,
        **{
            key: value
            for key, value in url.query.items()
            if key in {"sslmode", "sslrootcert", "sslcert", "sslkey"}
        },
    }


def client_command(args, command, database, *flags):
    options = connection_options(database)
    environment = os.environ.copy()
    for option, variable in (
        ("host", "PGHOST"),
        ("port", "PGPORT"),
        ("user", "PGUSER"),
        ("password", "PGPASSWORD"),
        ("sslmode", "PGSSLMODE"),
        ("sslrootcert", "PGSSLROOTCERT"),
        ("sslcert", "PGSSLCERT"),
        ("sslkey", "PGSSLKEY"),
    ):
        if options.get(option) is not None:
            environment[variable] = str(options[option])
    # Same-instance Docker tools are useful in CI without installing a client.
    # --env NAME copies the secret from this process environment, not the argv.
    if args.postgres_container:
        executable = shutil.which("docker")
        if not executable:
            raise ValueError("Docker CLI not found")
        environment["PGHOST"] = "127.0.0.1"
        environment["PGPORT"] = "5432"
        prefix = [executable, "exec", "-i"]
        for variable in ("PGHOST", "PGPORT", "PGUSER", "PGPASSWORD"):
            prefix += ["--env", variable]
        prefix += [args.postgres_container, command]
    else:
        executable = (
            str(Path(args.postgres_bin) / command)
            if args.postgres_bin
            else shutil.which(command)
        )
        if args.postgres_bin and os.name == "nt":
            executable += ".exe"
        if not executable or not Path(executable).is_file():
            raise ValueError(f"{command} not found; supply --postgres-bin")
        prefix = [executable]
    return [*prefix, "--dbname", str(database), *flags], environment


def private_directory(directory):
    destination = Path(directory).resolve()
    if destination.is_relative_to(REPO):
        raise ValueError("Backups must be kept outside the source repository")
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    return destination


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprints(connection):
    """Hash rows without exporting uploaded content, identities or tokens."""
    connection.execute("SET LOCAL statement_timeout = '120s'")
    connection.execute("SET LOCAL lock_timeout = '5s'")
    tables = connection.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    ).fetchall()
    result = {}
    for (table,) in tables:
        hashes = []
        with connection.cursor(name=f"paxveil_hash_{uuid.uuid4().hex}") as cursor:
            cursor.execute(
                sql.SQL("SELECT row_to_json(r)::text FROM public.{} AS r").format(
                    sql.Identifier(table)
                )
            )
            for (row,) in cursor:
                hashes.append(hashlib.sha256(row.encode("utf-8")).digest())
                if len(hashes) > 2_000_000:
                    raise ValueError(
                        "Verification row limit exceeded; use a streaming external audit"
                    )
        result[table] = {
            "rows": len(hashes),
            "sha256": hashlib.sha256(b"".join(sorted(hashes))).hexdigest(),
        }
    return result


def evidence(path, content):
    if path:
        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def backup(args):
    destination = private_directory(args.directory)
    basename = f"paxveil-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    archive = destination / f"{basename}.dump"
    manifest = destination / f"{basename}.json"
    partial = destination / f"{basename}.partial"
    partial.touch(mode=0o600)
    try:
        with psycopg.connect(**connection_options()) as connection:
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
            snapshot = connection.execute("SELECT pg_export_snapshot()").fetchone()[0]
            tables = fingerprints(connection)
            database = connection.info.dbname
            command, environment = client_command(
                args,
                "pg_dump",
                database,
                "--format=custom",
                f"--snapshot={snapshot}",
                "--no-owner",
                "--no-privileges",
            )
            with partial.open("wb") as output:
                result = subprocess.run(
                    command,
                    env=environment,
                    stdout=output,
                    stderr=subprocess.PIPE,
                    timeout=600,
                    check=False,
                )
            if result.returncode:
                raise RuntimeError(
                    "pg_dump failed; check matching PostgreSQL client and access"
                )
        partial.replace(archive)
        with manifest.open("x", encoding="utf-8") as stream:
            if os.name != "nt":
                manifest.chmod(0o600)
            json.dump(
                {
                    "format": "PAXVEIL private backup v1",
                    "created_at": datetime.now(UTC).isoformat(),
                    "archive_sha256": checksum(archive),
                    "archive_bytes": archive.stat().st_size,
                    "tables": tables,
                },
                stream,
                indent=2,
            )
            stream.write("\n")
        removed = rotate_backups(destination, args.retain_days, manifest)
        print(
            json.dumps(
                {
                    "backup": "created",
                    "archive": str(archive),
                    "manifest": str(manifest),
                    "table_count": len(tables),
                    "retention_days": args.retain_days,
                    "removed_backup_pairs": removed,
                }
            )
        )
    finally:
        if partial.exists():
            partial.unlink()


def rotate_backups(directory, retain_days, newest):
    """Remove only recognized backup pairs after a new backup was completed."""
    cutoff = datetime.now(UTC) - timedelta(days=retain_days)
    removed = 0
    for manifest in directory.glob("paxveil-*.json"):
        if (
            manifest == newest
            or manifest.is_symlink()
            or manifest.resolve().parent != directory
        ):
            continue
        if not re.fullmatch(r"paxveil-\d{8}T\d{6}Z-[a-f0-9]{8}\.json", manifest.name):
            continue
        archive = manifest.with_suffix(".dump")
        if (
            not archive.is_file()
            or archive.is_symlink()
            or archive.resolve().parent != directory
        ):
            continue
        try:
            metadata = json.loads(manifest.read_text(encoding="utf-8"))
            created = datetime.fromisoformat(metadata["created_at"])
            if created.tzinfo is None:
                continue
            recognized = (
                metadata["format"] == "PAXVEIL private backup v1"
                and checksum(archive) == metadata["archive_sha256"]
            )
        except (OSError, KeyError, ValueError, TypeError):
            continue
        if recognized and created < cutoff:
            archive.unlink()
            manifest.unlink()
            removed += 1
    return removed


class DisposableDatabase:
    def __init__(self, prefix):
        self.name = f"{prefix}_{uuid.uuid4().hex}"
        self.marker = f"PAXVEIL disposable verification {uuid.uuid4().hex}"
        self.created = False

    def __enter__(self):
        with psycopg.connect(
            **connection_options("postgres"), autocommit=True
        ) as connection:
            connection.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(self.name))
            )
            self.created = True
            connection.execute(
                sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                    sql.Identifier(self.name), sql.Literal(self.marker)
                )
            )
        return self.name

    def __exit__(self, exc_type, exc, traceback):
        if not self.created:
            return
        with psycopg.connect(
            **connection_options("postgres"), autocommit=True
        ) as connection:
            marker = connection.execute(
                "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname=%s",
                (self.name,),
            ).fetchone()
            if marker != (self.marker,) or not self.name.startswith(
                ("paxveil_restore_verify_", "paxveil_verify_")
            ):
                raise RuntimeError(
                    "Disposable database identity changed; cleanup refused"
                )
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                    sql.Identifier(self.name)
                )
            )


def verify_backup(args):
    archive = Path(args.archive).resolve()
    manifest = json.loads(archive.with_suffix(".json").read_text(encoding="utf-8"))
    if manifest.get("format") != "PAXVEIL private backup v1" or checksum(
        archive
    ) != manifest.get("archive_sha256"):
        raise ValueError("Backup manifest/checksum mismatch")
    with DisposableDatabase("paxveil_restore_verify") as database:
        command, environment = client_command(
            args,
            "pg_restore",
            database,
            "--exit-on-error",
            "--no-owner",
            "--no-privileges",
        )
        with archive.open("rb") as source:
            result = subprocess.run(
                command,
                env=environment,
                stdin=source,
                capture_output=True,
                timeout=600,
                check=False,
            )
        if result.returncode:
            raise RuntimeError("pg_restore failed; working database was not changed")
        with psycopg.connect(**connection_options(database)) as connection:
            restored = fingerprints(connection)
        if restored != manifest["tables"]:
            raise RuntimeError("Restored table rows do not match the exported snapshot")
    report = {
        "verified_at": datetime.now(UTC).isoformat(),
        "operation": "isolated PostgreSQL dump/restore",
        "result": "passed",
        "archive_bytes": manifest["archive_bytes"],
        "table_count": len(restored),
        "row_count": sum(t["rows"] for t in restored.values()),
        "all_table_fingerprints_match": True,
        "disposable_database_removed": True,
        "working_database_mutated": False,
    }
    evidence(args.evidence, report)
    print(json.dumps(report))


def verify_concurrency(args):
    with DisposableDatabase("paxveil_verify") as database:
        # No production objects are imported before the replacement DSN is set.
        url = make_url(get_settings().database_url).set(database=database)
        environment = os.environ.copy()
        environment["DATABASE_URL"] = url.render_as_string(hide_password=False)
        command = [sys.executable, "-m", "alembic", "upgrade", "head"]
        migration = subprocess.run(
            command,
            env=environment,
            cwd=REPO / "backend",
            capture_output=True,
            timeout=120,
            check=False,
        )
        if migration.returncode:
            raise RuntimeError(
                "Migrations failed in the disposable verification database"
            )
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "_concurrency-child"],
            env=environment,
            cwd=REPO / "backend",
            capture_output=True,
            timeout=120,
            check=False,
        )
        if result.returncode:
            raise RuntimeError("PostgreSQL concurrency verification failed")
        report = json.loads(result.stdout)
    report.update(
        {
            "verified_at": datetime.now(UTC).isoformat(),
            "disposable_database_removed": True,
            "working_database_mutated": False,
        }
    )
    evidence(args.evidence, report)
    print(json.dumps(report))


def concurrency_child():
    if not connection_options()["dbname"].startswith("paxveil_verify_"):
        raise ValueError("Concurrency child refuses a non-verification database")
    from paxveil import worker
    from paxveil.api import enqueue_scan
    from paxveil.db import (
        Advisory,
        Dependency,
        Job,
        Package,
        PackageVersion,
        Project,
        RequestLimit,
        Scan,
        SessionLocal,
        User,
        engine,
        now,
    )
    from paxveil.resources import request_window
    from sqlalchemy import func, select

    # Independent connections must share one durable allowance, including after
    # rejection and when the next fixed window starts. No API process-local
    # memory or clock sleeps participate in this check.
    request_identity = f"verify_{uuid.uuid4().hex}"
    request_at = now().replace(microsecond=0)
    request_maximum = 11
    request_attempts = 64

    def request_limit(_):
        with SessionLocal.begin() as db:
            return request_window(
                db, "verification", request_identity, request_maximum, at=request_at
            )

    with ThreadPoolExecutor(max_workers=8) as pool:
        request_results = list(pool.map(request_limit, range(request_attempts)))
    assert sum(accepted for accepted, _ in request_results) == request_maximum, (
        "Independent PostgreSQL connections exceeded or lost the shared request allowance"
    )
    expected_retry = 60 - int(request_at.timestamp()) % 60
    assert all(retry == expected_retry for _, retry in request_results)
    with SessionLocal.begin() as db:
        counts = db.scalars(select(RequestLimit.count)).all()
        assert counts == [request_maximum], (
            "Rejected requests increased the durable counter"
        )
        accepted, retry_after = request_window(
            db,
            "verification",
            request_identity,
            request_maximum,
            at=request_at + timedelta(seconds=expected_retry),
        )
        assert accepted and retry_after == 60, "A fresh request window did not recover"
        assert sorted(db.scalars(select(RequestLimit.count)).all()) == [
            1,
            request_maximum,
        ]

    with SessionLocal.begin() as db:
        owner = User(username=f"verify_{uuid.uuid4().hex}")
        db.add(owner)
        db.flush()
        project = Project(
            user_id=owner.id,
            name="Isolated concurrency test",
            filename="requirements.txt",
            content=b"requests==2.31.0\n",
        )
        db.add(project)
        db.flush()
        owner_id, project_id = owner.id, project.id

    def enqueue(_):
        with SessionLocal.begin() as db:
            return enqueue_scan(db, db.get(Project, project_id)).id

    with ThreadPoolExecutor(max_workers=8) as pool:
        enqueued = list(pool.map(enqueue, range(24)))
    assert len(set(enqueued)) == 1, "Concurrent enqueue created duplicate scan jobs"
    with SessionLocal.begin() as db:
        existing = db.get(Job, enqueued[0])
        existing.status = "succeeded"
        for _ in range(24):
            scan = Scan(project_id=project_id)
            db.add(scan)
            db.flush()
            db.add(
                Job(
                    user_id=owner_id,
                    project_id=project_id,
                    scan_id=scan.id,
                    kind="scan",
                )
            )

    def claim(_):
        return worker.claim_job()

    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(claim, range(40)))
    claimed = [claim for claim in claims if claim]
    assert len(claimed) == 24 and len({claim[0] for claim in claimed}) == 24, (
        "SKIP LOCKED claim lost or duplicated work"
    )
    assert len({claim[1] for claim in claimed}) == 24, (
        "Claims require unique fencing tokens"
    )
    stale_id, stale_token = claimed[0]
    with SessionLocal.begin() as db:
        db.get(Job, stale_id).lease_until = now() - timedelta(seconds=1)
    successor = worker.claim_job()
    assert successor[0] == stale_id and successor[1] != stale_token, (
        "Lease recovery did not fence the prior claim"
    )

    async def controlled_scan(*args, **kwargs):
        return {
            "completeness": "complete",
            "dependencies": [],
            "findings": [],
            "sources": [],
            "marker": "isolated-test",
        }

    import paxveil.core.service as core

    original = core.scan
    core.scan = controlled_scan
    try:
        asyncio.run(worker.execute(*successor))
        with SessionLocal() as db:
            before = db.get(Job, stale_id).result
            assert db.get(Job, stale_id).status == "succeeded"
        asyncio.run(worker.execute(stale_id, stale_token))
        with SessionLocal() as db:
            saved = db.get(Job, stale_id)
            assert (
                saved.status == "succeeded"
                and saved.claim_token == successor[1]
                and saved.result == before
            ), "Stale worker overwrote successor"
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(Job)
                    .where(Job.id == stale_id, Job.attempts == 2)
                )
                == 1
            )
    finally:
        core.scan = original

    def fresh_owner_job():
        with SessionLocal.begin() as db:
            owner = User(username=f"verify_{uuid.uuid4().hex}")
            db.add(owner)
            db.flush()
            project = Project(
                user_id=owner.id,
                name="Deletion race",
                filename="requirements.txt",
                content=b"example==1.0\n",
            )
            db.add(project)
            db.flush()
            scan = Scan(project_id=project.id)
            db.add(scan)
            db.flush()
            job = Job(
                user_id=owner.id, project_id=project.id, scan_id=scan.id, kind="scan"
            )
            db.add(job)
            db.flush()
            return owner.id, project.id, scan.id, job.id

    deletion_owner, deletion_project, deletion_scan, deletion_job = fresh_owner_job()
    entered = Event()
    original_owner_lock = worker.lock_owner

    def observed_owner_lock(db, identifier):
        if identifier == deletion_owner:
            entered.set()
        return original_owner_lock(db, identifier)

    worker.lock_owner = observed_owner_lock
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with SessionLocal.begin() as db:
                user = db.scalar(
                    select(User).where(User.id == deletion_owner).with_for_update()
                )
                future = pool.submit(worker.claim_job)
                assert entered.wait(5), "Claim did not reach the held owner lock"
                assert not future.done(), "Claim ignored the held deletion lock"
                db.delete(user)
                db.flush()
            assert future.result(timeout=10) is None, (
                "Claim resurrected deleted owner work"
            )
    finally:
        worker.lock_owner = original_owner_lock
    with SessionLocal() as db:
        assert (
            db.get(Project, deletion_project) is None
            and db.get(Scan, deletion_scan) is None
            and db.get(Job, deletion_job) is None
        )

    for fail_after_delete in (False, True):
        deletion_owner, _, _, deletion_job = fresh_owner_job()
        claim = worker.claim_job()
        assert claim[0] == deletion_job
        started, finish = Event(), Event()

        async def late_scan(
            *args,
            started=started,
            finish=finish,
            fail_after_delete=fail_after_delete,
            **kwargs,
        ):
            started.set()
            assert await asyncio.to_thread(finish.wait, 10), (
                "Deletion test did not release analysis"
            )
            if fail_after_delete:
                raise ValueError("Controlled failure after owner deletion")
            return await controlled_scan()

        core.scan = late_scan
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, worker.execute(*claim))
                assert started.wait(5)
                with SessionLocal.begin() as db:
                    user = db.scalar(
                        select(User).where(User.id == deletion_owner).with_for_update()
                    )
                    db.delete(user)
                finish.set()
                future.result(timeout=10)
            with SessionLocal() as db:
                assert (
                    db.get(User, deletion_owner) is None
                    and db.get(Job, deletion_job) is None
                )
        finally:
            finish.set()
            core.scan = original

    reference_targets = [fresh_owner_job() for _ in range(2)]

    def ingest_shared_references(index):
        owner_id, _, scan_id, _ = reference_targets[index]
        dependencies = [
            {"name": "verify-alpha", "version": "1"},
            {"name": "verify-beta", "version": "1"},
        ]
        if index:
            dependencies.reverse()
        report = {
            "dependencies": dependencies,
            "findings": [
                {
                    "id": f"VERIFY-ADVISORY-{number}",
                    "package": "verify-alpha",
                    "version": "1",
                }
                for number in (reversed(range(2)) if index else range(2))
            ],
        }
        with SessionLocal.begin() as db:
            original_owner_lock(db, owner_id)
            worker.ingest(db, db.get(Scan, scan_id), report)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(ingest_shared_references, range(2)))
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Package)) == 2
        assert db.scalar(select(func.count()).select_from(PackageVersion)) == 2
        assert db.scalar(select(func.count()).select_from(Dependency)) == 4
        assert db.scalar(select(func.count()).select_from(Advisory)) == 2
    engine.dispose()
    print(
        json.dumps(
            {
                "operation": "real PostgreSQL concurrent queue verification",
                "result": "passed",
                "threads": 8,
                "enqueue_requests": 24,
                "deduplicated_jobs": 1,
                "pending_jobs": 24,
                "claim_attempts": 40,
                "unique_claims": 24,
                "lease_recovery": "passed",
                "stale_claim_fencing": "passed",
                "account_deletion_during_claim": "passed",
                "account_deletion_during_success": "passed",
                "account_deletion_during_failure": "passed",
                "concurrent_shared_catalog_upsert": "passed",
                "shared_request_counter_attempts": request_attempts,
                "shared_request_counter_accepted": request_maximum,
                "shared_request_counter_rejection_bound": "passed",
                "shared_request_counter_window_recovery": "passed",
                "source_queries": 0,
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="operation", required=True)
    create = subcommands.add_parser("backup")
    create.add_argument(
        "--directory",
        required=True,
        help="Private destination outside the source repository",
    )
    create.add_argument(
        "--retain-days",
        type=int,
        default=7,
        help="Remove recognized older backup pairs only after a successful backup",
    )
    restore = subcommands.add_parser("verify-backup")
    restore.add_argument("--archive", required=True)
    restore.add_argument("--evidence")
    concurrency = subcommands.add_parser("verify-concurrency")
    concurrency.add_argument("--evidence")
    subcommands.add_parser("_concurrency-child", help=argparse.SUPPRESS)
    for command in (create, restore):
        clients = command.add_mutually_exclusive_group()
        clients.add_argument(
            "--postgres-bin",
            "--pg-bin",
            dest="postgres_bin",
            help="Existing matching PostgreSQL client binary directory",
        )
        clients.add_argument(
            "--postgres-container",
            help="Existing same-instance PostgreSQL Docker container name/ID",
        )
    for command in (create, restore, concurrency):
        command.add_argument(
            "--env", help="Local environment file (only DATABASE_URL is read)"
        )
    args = parser.parse_args()
    try:
        if getattr(args, "env", None):
            from dotenv import dotenv_values

            values = dotenv_values(Path(args.env).resolve(), interpolate=False)
            if not values.get("DATABASE_URL"):
                raise ValueError("Selected environment has no DATABASE_URL")
            os.environ["DATABASE_URL"] = values["DATABASE_URL"]
            get_settings.cache_clear()
        if getattr(args, "retain_days", 7) < 1:
            raise ValueError("Backup retention must be at least one day")
        {
            "backup": backup,
            "verify-backup": verify_backup,
            "verify-concurrency": verify_concurrency,
            "_concurrency-child": lambda _: concurrency_child(),
        }[args.operation](args)
    except Exception as exc:  # noqa: BLE001 -- never export a DSN-bearing traceback
        # Exception strings/tracebacks can contain DSNs or private manifest data.
        print(
            json.dumps(
                {
                    "operation": args.operation,
                    "result": "failed",
                    "error_type": type(exc).__name__,
                    "action": "Check PostgreSQL access, tool version and supplied private paths; no credentials are exported",
                }
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
