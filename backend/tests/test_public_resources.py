"""Public-user quotas, shared counters and private data lifecycle."""

import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import insert, select
from test_api import api_env, fixture_report  # noqa: F401 -- isolated shared fixture


def test_atomic_counter_shared_between_connections_and_recovers_next_window(api_env):  # noqa: F811
    resources = importlib.import_module("paxveil.resources")
    instant = api_env.db.now().replace(second=0, microsecond=0)

    def consume(_):
        with api_env.factory.begin() as db:
            return resources.request_window(db, "test", "private-identity", 7, at=instant)[0]

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(consume, range(24)))
    assert sum(outcomes) == 7
    with api_env.factory.begin() as db:
        record = db.scalar(select(api_env.db.RequestLimit))
        assert record.count == 7 and "private-identity" not in record.key_hash
        assert resources.request_window(db, "test", "private-identity", 7, at=instant + timedelta(minutes=1))[0]
        assert resources.request_window(db, "test", "other-identity", 7, at=instant)[0]


def test_project_active_job_and_hourly_budget_are_owner_scoped(api_env, monkeypatch):  # noqa: F811
    owner, other = api_env.owner(), api_env.owner("other")
    client = api_env.client(owner)
    monkeypatch.setattr(api_env.settings, "max_projects_per_user", 1)
    upload = {"data": {"name": "First"}, "files": {"file": ("requirements.txt", b"requests==2.31.0")}}
    first = client.post("/api/projects", **upload)
    assert first.status_code == 201
    assert client.post("/api/projects", **upload).json()["detail"]["code"] == "project_limit"
    monkeypatch.setattr(api_env.settings, "max_projects_per_user", 10)
    monkeypatch.setattr(api_env.settings, "max_active_jobs_per_user", 1)
    rejected = client.post("/api/projects", **upload)
    assert rejected.status_code == 429 and rejected.json()["detail"]["code"] == "active_job_limit"
    assert len(client.get("/api/projects").json()) == 1  # rejected creation rolls back
    assert api_env.client(other).post("/api/projects", **upload).status_code == 201
    with api_env.factory.begin() as db:
        job = db.scalar(select(api_env.db.Job).where(api_env.db.Job.user_id == owner.id))
        job.status = "succeeded"
    monkeypatch.setattr(api_env.settings, "max_analysis_jobs_per_hour", 1)
    rejected = client.post(f"/api/projects/{first.json()['id']}/scan")
    assert rejected.status_code == 429 and rejected.json()["detail"]["code"] == "analysis_limit"
    with api_env.factory.begin() as db:
        job = db.scalar(select(api_env.db.Job).where(api_env.db.Job.user_id == owner.id))
        job.created_at = api_env.db.now() - timedelta(hours=2)
    assert client.post(f"/api/projects/{first.json()['id']}/scan").status_code == 200


def test_storage_quota_prevents_new_work_without_losing_existing_project(api_env, monkeypatch):  # noqa: F811
    owner = api_env.owner()
    project, _, _ = api_env.project(owner, report=fixture_report())
    monkeypatch.setattr(api_env.settings, "max_owner_storage_bytes", 1)
    response = api_env.client(owner).post(f"/api/projects/{project.id}/scan")
    assert response.status_code == 429 and response.json()["detail"]["code"] == "storage_limit"
    assert api_env.client(owner).get(f"/api/projects/{project.id}").status_code == 200


def test_export_is_private_and_account_delete_cascades_sessions_data(api_env):  # noqa: F811
    alice, bob = api_env.owner("alice", 555), api_env.owner("bob", 666)
    project, scan, job = api_env.project(alice, report=fixture_report(), watch=True)
    foreign, _, _ = api_env.project(bob, report=fixture_report())
    client = api_env.client(alice)
    code = client.post("/api/auth/telegram/link").json()["code"]
    response = client.get("/api/account/export")
    assert response.status_code == 200
    exported = response.json()
    assert exported["account"]["id"] == alice.id
    assert [item["id"] for item in exported["projects"]] == [project.id]
    assert exported["projects"][0]["content"] == "fixture-package==1.0\n"
    assert exported["projects"][0]["scans"][0]["report"]["findings"]
    for secret in (code, "token_hash", "code_hash", "pbkdf2_sha256", "synthetic-password-1234", foreign.id):
        assert secret not in response.text
    assert client.request("DELETE", "/api/account", json={"confirmation": "wrong"}).status_code == 422
    assert client.get("/api/auth/me").status_code == 200
    deleted = client.request("DELETE", "/api/account", json={"confirmation": "DELETE"})
    assert deleted.status_code == 200 and deleted.json() == {"ok": True}
    assert client.get("/api/auth/me").status_code == 401
    with api_env.factory() as db:
        assert db.get(api_env.db.User, alice.id) is None
        assert db.get(api_env.db.Project, project.id) is None
        assert db.get(api_env.db.Scan, scan.id) is None
        assert db.get(api_env.db.Job, job.id) is None
        assert db.scalar(select(api_env.db.Session).where(api_env.db.Session.user_id == alice.id)) is None
        assert db.scalar(select(api_env.db.LinkCode).where(api_env.db.LinkCode.user_id == alice.id)) is None
        assert db.get(api_env.db.Project, foreign.id) is not None


def test_session_refreshes_are_bounded_and_expired_sessions_removed(api_env, monkeypatch):  # noqa: F811
    owner = api_env.owner()
    monkeypatch.setattr(api_env.settings, "max_sessions_per_user", 3)
    first = None
    with api_env.factory() as db:
        user = db.get(api_env.db.User, owner.id)
        for index in range(6):
            token = api_env.auth.new_session(db, user)
            if index == 0:
                first = api_env.auth.digest(token)
        active = db.scalars(select(api_env.db.Session).where(api_env.db.Session.user_id == owner.id)).all()
        assert len(active) == 3 and db.get(api_env.db.Session, first) is None
        active[0].expires_at = api_env.db.now() - timedelta(seconds=1)
        expired = active[0].token_hash
        db.commit()
        api_env.auth.new_session(db, user)
        assert db.get(api_env.db.Session, expired) is None
        assert len(db.scalars(select(api_env.db.Session).where(api_env.db.Session.user_id == owner.id)).all()) == 3


def test_cleanup_preserves_active_work_and_complete_watch_baseline(api_env, monkeypatch):  # noqa: F811
    resources = importlib.import_module("paxveil.resources")
    monkeypatch.setattr(api_env.settings, "retained_scans_per_project", 2)
    owner = api_env.owner()
    project, baseline, _ = api_env.project(owner, report=fixture_report())
    instant = api_env.db.now()
    obsolete_ids = []
    with api_env.factory.begin() as db:
        db.get(api_env.db.Scan, baseline.id).created_at = instant - timedelta(days=40)
        for index in range(5):
            scan = api_env.db.Scan(
                project_id=project.id,
                status="partial",
                report={"sources": [{"name": "OSV", "status": "error"}], "vulnerability_lookup_complete": False},
                created_at=instant - timedelta(days=4 - index),
            )
            db.add(scan)
            db.flush()
            obsolete_ids.append(scan.id)
            db.add(api_env.db.SourceSnapshot(scan_id=scan.id, source="OSV", data={"status": "error"}))
        active = api_env.db.Scan(project_id=project.id, status="running", created_at=instant - timedelta(days=50))
        db.add(active)
        db.flush()
        db.add(
            api_env.db.Job(user_id=owner.id, project_id=project.id, scan_id=active.id, kind="scan", status="running")
        )
        db.add(
            api_env.db.LinkCode(
                code_hash="expired-fixture", user_id=owner.id, expires_at=instant - timedelta(minutes=1)
            )
        )
    with api_env.factory.begin() as db:
        removed = resources.cleanup(db, api_env.settings, at=instant)
        assert removed["scans"] == 3 and removed["telegram_link_codes"] == 1
    with api_env.factory() as db:
        assert db.get(api_env.db.Scan, baseline.id) is not None
        assert db.get(api_env.db.Scan, active.id) is not None
        assert db.get(api_env.db.Scan, obsolete_ids[-1]) is not None
        assert db.get(api_env.db.Scan, obsolete_ids[0]) is None
        assert len(db.scalars(select(api_env.db.SourceSnapshot)).all()) == 2


def test_upload_environment_preferences_are_validated_and_returned(api_env):  # noqa: F811
    client = api_env.client(api_env.owner())
    assert client.get("/api/settings").json()["upload_python_version"] == "3.11"
    assert (
        client.put("/api/settings", json={"upload_python_version": "3.12", "upload_platform": "windows"}).json()[
            "upload_platform"
        ]
        == "windows"
    )
    assert client.put("/api/settings", json={"upload_python_version": "2.7"}).status_code == 422
    assert client.put("/api/settings", json={"upload_platform": "android"}).status_code == 422


def test_export_requests_are_limited_without_revoking_account(api_env):  # noqa: F811
    client = api_env.client(api_env.owner())
    for _ in range(3):
        assert client.get("/api/account/export").status_code == 200
    response = client.get("/api/account/export")
    assert response.status_code == 429 and response.json()["detail"]["code"] == "export_limit"
    assert client.get("/api/auth/me").status_code == 200


def test_api_counter_applies_across_clients_without_blocking_health_or_other_owner(api_env, monkeypatch):  # noqa: F811
    resources = importlib.import_module("paxveil.resources")
    instant = api_env.db.now()
    monkeypatch.setattr(resources, "now", lambda: instant)
    monkeypatch.setattr(api_env.api, "now", lambda: instant)
    owner, other = api_env.owner(), api_env.owner("other")
    with api_env.factory.begin() as db:
        for _ in range(240):
            assert resources.request_window(db, "api", f"account:{owner.id}", 240)[0]
    for client in (api_env.client(owner), api_env.client(owner)):
        response = client.get("/api/projects")
        assert response.status_code == 429 and response.json()["detail"]["code"] == "request_limit"
        assert int(response.headers["retry-after"]) >= 1
        assert client.get("/api/health").status_code == 200
    assert api_env.client(other).get("/api/projects").status_code == 200


def test_cleanup_batch_rotates_to_previously_unprocessed_owners(api_env):  # noqa: F811
    resources = importlib.import_module("paxveil.resources")
    instant = api_env.db.now()
    with api_env.factory.begin() as db:
        for index in range(101):
            db.add(api_env.db.User(username=f"batch_owner_{index}"))
    with api_env.factory.begin() as db:
        resources.cleanup(db, api_env.settings, at=instant)
        assert (
            len(db.scalars(select(api_env.db.User.id).where(api_env.db.User.last_maintenance_at.is_(None))).all()) == 1
        )
    with api_env.factory.begin() as db:
        resources.cleanup(db, api_env.settings, at=instant + timedelta(minutes=5))
        assert db.scalar(select(api_env.db.User.id).where(api_env.db.User.last_maintenance_at.is_(None))) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("quota", ["max_report_bytes", "max_owner_storage_bytes"])
async def test_worker_resource_failure_is_terminal_without_persisting_large_report(api_env, monkeypatch, quota):  # noqa: F811
    worker = importlib.import_module("paxveil.worker")
    service = importlib.import_module("paxveil.core.service")
    monkeypatch.setattr(worker, "SessionLocal", api_env.factory)
    monkeypatch.setattr(worker, "settings", api_env.settings)
    monkeypatch.setattr(api_env.settings, quota, 1)

    async def analyze(*args, **kwargs):
        return fixture_report()

    monkeypatch.setattr(service, "scan", analyze)
    owner = api_env.owner()
    _, scan, job = api_env.project(owner, run_at=api_env.db.now() - timedelta(seconds=1))
    claim = worker.claim_job()
    assert claim[0] == job.id
    await worker.execute(*claim)
    with api_env.factory() as db:
        result = db.get(api_env.db.Job, job.id)
        assert result.status == "failed" and result.attempts == 1 and result.result is None
        assert "лимит" in result.error
        assert db.get(api_env.db.Scan, scan.id).report is None
        assert db.scalar(select(api_env.db.Dependency)) is None


def test_status_transition_caps_history_preserves_latest_and_other_owner(api_env):  # noqa: F811
    owner, other = api_env.owner(), api_env.owner("other")
    project, _, _ = api_env.project(owner, report=fixture_report())
    foreign, _, _ = api_env.project(other, report=fixture_report())
    instant = api_env.db.now() - timedelta(days=1)
    with api_env.factory.begin() as db:
        state = api_env.db.FindingState(
            project_id=project.id, advisory_id="TEST-ONLY-ADVISORY", package="fixture-package", status="open"
        )
        other_state = api_env.db.FindingState(
            project_id=foreign.id, advisory_id="TEST-ONLY-ADVISORY", package="fixture-package", status="investigating"
        )
        db.add_all([state, other_state])
        db.flush()
        state_id, other_state_id = state.id, other_state.id
        db.execute(
            insert(api_env.db.StatusHistory),
            [
                {
                    "state_id": state_id,
                    "old_status": "open" if index % 2 == 0 else "investigating",
                    "new_status": "investigating" if index % 2 == 0 else "open",
                    "changed_at": instant,
                }
                for index in range(1000)
            ],
        )
        db.add(
            api_env.db.StatusHistory(
                state_id=other_state_id, old_status="open", new_status="investigating", changed_at=instant
            )
        )
        first_id = db.scalar(
            select(api_env.db.StatusHistory.id)
            .where(api_env.db.StatusHistory.state_id == state_id)
            .order_by(api_env.db.StatusHistory.id)
        )
    client = api_env.client(owner)
    response = client.put(
        f"/api/projects/{project.id}/finding-status",
        json={"advisory_id": "TEST-ONLY-ADVISORY", "package": "fixture-package", "status": "accepted"},
    )
    assert response.status_code == 200 and response.json()["status"] == "accepted"
    with api_env.factory() as db:
        history = db.scalars(
            select(api_env.db.StatusHistory)
            .where(api_env.db.StatusHistory.state_id == state_id)
            .order_by(api_env.db.StatusHistory.id)
        ).all()
        assert len(history) == 1000
        assert db.get(api_env.db.StatusHistory, first_id) is None
        assert history[0].id == first_id + 1
        assert history[-1].old_status == "open" and history[-1].new_status == "accepted"
        assert db.get(api_env.db.FindingState, state_id).status == "accepted"
        assert db.get(api_env.db.FindingState, other_state_id).status == "investigating"
        assert (
            len(
                db.scalars(
                    select(api_env.db.StatusHistory).where(api_env.db.StatusHistory.state_id == other_state_id)
                ).all()
            )
            == 1
        )
    # Repeating the current status creates no transition or history churn.
    assert (
        client.put(
            f"/api/projects/{project.id}/finding-status",
            json={"advisory_id": "TEST-ONLY-ADVISORY", "package": "fixture-package", "status": "accepted"},
        ).status_code
        == 200
    )
    with api_env.factory() as db:
        assert (
            len(
                db.scalars(
                    select(api_env.db.StatusHistory.id).where(api_env.db.StatusHistory.state_id == state_id)
                ).all()
            )
            == 1000
        )


def test_cleanup_caps_existing_history_per_project_and_counts_it_in_storage(api_env, monkeypatch):  # noqa: F811
    resources = importlib.import_module("paxveil.resources")
    owner = api_env.owner()
    first, _, _ = api_env.project(owner, report=fixture_report())
    second, _, _ = api_env.project(owner, report=fixture_report())
    monkeypatch.setattr(api_env.settings, "retained_status_changes_per_project", 10)
    instant = api_env.db.now() - timedelta(days=1)
    with api_env.factory.begin() as db:
        initial_bytes = resources.owner_storage(db, owner.id)
        states = [
            api_env.db.FindingState(
                project_id=project.id, advisory_id="TEST-ONLY-ADVISORY", package="fixture-package", status="accepted"
            )
            for project in (first, second)
        ]
        db.add_all(states)
        db.flush()
        with_states = resources.owner_storage(db, owner.id)
        assert with_states > initial_bytes
        for state in states:
            db.execute(
                insert(api_env.db.StatusHistory),
                [
                    {
                        "state_id": state.id,
                        "old_status": "open",
                        "new_status": "accepted",
                        "changed_at": instant + timedelta(seconds=index),
                    }
                    for index in range(15)
                ],
            )
        before = resources.owner_storage(db, owner.id)
        assert before > with_states
        counts = resources.cleanup(db, api_env.settings)
        assert counts["finding_status_history"] == 10
        after = resources.owner_storage(db, owner.id)
        assert with_states < after < before
        for state in states:
            retained = db.scalars(
                select(api_env.db.StatusHistory)
                .where(api_env.db.StatusHistory.state_id == state.id)
                .order_by(api_env.db.StatusHistory.changed_at)
            ).all()
            assert len(retained) == 10 and retained[0].changed_at.replace(tzinfo=instant.tzinfo) == instant + timedelta(
                seconds=5
            )
            assert state.status == "accepted"
