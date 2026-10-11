"""Durable outbox/worker tests using controlled advisory and Telegram fixtures."""

from __future__ import annotations

import asyncio
import copy
import importlib
import json
from datetime import UTC, datetime, timedelta
from functools import partial

import httpx
import pytest
from sqlalchemy import select
from test_api import api_env, fixture_report  # noqa: F401 -- pytest fixture shared with isolated API tests

INSTANT = datetime(2026, 10, 10, 10, 0, tzinfo=UTC)


@pytest.fixture
def outbox(api_env, monkeypatch):  # noqa: F811 -- pytest resolves the imported fixture by name
    notifications = importlib.import_module("paxveil.notifications")
    worker = importlib.import_module("paxveil.worker")
    monkeypatch.setattr(worker, "SessionLocal", api_env.factory)
    monkeypatch.setattr(worker, "settings", api_env.settings)
    monkeypatch.setattr(worker, "now", lambda: INSTANT)
    monkeypatch.setattr(notifications, "now", lambda: INSTANT)
    # ORM timestamp defaults retain the real clock; make fixture jobs due for the
    # frozen worker instead of accidentally depending on today's calendar date.
    api_env.project = partial(api_env.project, run_at=INSTANT)
    monkeypatch.setattr(api_env.settings, "telegram_token", "synthetic-outbox-token")
    original_client = httpx.AsyncClient
    sent = []
    response_queue = []

    def transport(request):
        assert request.url.host == "api.telegram.org"
        assert request.url.scheme == "https"
        assert request.url.path == "/botsynthetic-outbox-token/sendMessage"
        sent.append(json.loads(request.content))
        response = (
            response_queue.pop(0)
            if response_queue
            else (200, {"ok": True, "result": {"message_id": 1}})
        )
        if isinstance(response, Exception):
            raise response
        status, body = response
        return httpx.Response(status, json=body)

    def mock_client(**kwargs):
        return original_client(transport=httpx.MockTransport(transport), **kwargs)

    monkeypatch.setattr(worker.httpx, "AsyncClient", mock_client)

    def add(user, project, *, status="pending", category="new", priority=80, key=None):
        with api_env.factory.begin() as db:
            notification = api_env.db.Notification(
                user_id=user.id,
                project_id=project.id,
                event_key=key or api_env.db.uid(),
                category=category,
                payload={
                    "project_name": project.name,
                    "finding": fixture_report(priority)["findings"][0],
                },
                status=status,
                run_at=INSTANT - timedelta(seconds=1),
            )
            db.add(notification)
            db.flush()
            return notification.id

    api_env.worker = worker
    api_env.notifications = notifications
    api_env.sent = sent
    api_env.responses = response_queue
    api_env.http_client = original_client
    api_env.add = add
    return api_env


def test_quiet_hours_timezone_midnight_dst_and_daily_digest(outbox):
    delivery_time = outbox.notifications.delivery_time
    at = datetime(2026, 10, 10, 20, 30, tzinfo=UTC)
    assert delivery_time(
        {"timezone": "Europe/Moscow", "quiet_start": "22:00", "quiet_end": "08:00"}, at
    ) == datetime(2026, 10, 11, 5, 0, tzinfo=UTC)
    daytime = {"timezone": "UTC", "quiet_start": "12:00", "quiet_end": "13:00"}
    assert delivery_time(
        daytime, datetime(2026, 10, 10, 12, 15, tzinfo=UTC)
    ) == datetime(2026, 10, 10, 13, 0, tzinfo=UTC)
    assert delivery_time(
        {"timezone": "Europe/Moscow", "digest": True}, INSTANT
    ) == datetime(2026, 10, 11, 6, 0, tzinfo=UTC)
    transition = datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    assert delivery_time(
        {"timezone": "Europe/Berlin", "quiet_start": "22:00", "quiet_end": "08:00"},
        transition,
    ) == datetime(2026, 10, 25, 7, 0, tzinfo=UTC)


def test_event_diff_categories_threshold_and_database_deduplication(outbox):
    owner = outbox.owner(telegram_id=555)
    project, _, _ = outbox.project(owner, watch=True)
    before = fixture_report(50)
    after = copy.deepcopy(before)
    after["findings"][0].update(priority=80, fixed_versions=["1.1"], kev=True)
    changes = list(outbox.notifications.event_changes(before, after))
    assert {category for category, _ in changes} == {"priority", "fix", "exploitation"}
    with outbox.factory.begin() as db:
        user = db.get(outbox.db.User, owner.id)
        item = db.get(outbox.db.Project, project.id)
        outbox.notifications.schedule_events(db, item, user, before, after)
        outbox.notifications.schedule_events(db, item, user, before, after)
    with outbox.factory() as db:
        notifications = db.scalars(select(outbox.db.Notification)).all()
        assert len(notifications) == 3
        assert {n.user_id for n in notifications} == {owner.id}
        assert len({n.event_key for n in notifications}) == 3


def test_disabled_event_categories_and_threshold_create_no_outbox_rows(outbox):
    owner = outbox.owner(telegram_id=555)
    project, _, _ = outbox.project(owner, watch=True)
    with outbox.factory.begin() as db:
        user = db.get(outbox.db.User, owner.id)
        user.preferences = {
            **user.preferences,
            "minimum_priority": 90,
            "categories": ["new"],
        }
        outbox.notifications.schedule_events(
            db,
            db.get(outbox.db.Project, project.id),
            user,
            {"findings": []},
            fixture_report(80),
        )
    with outbox.factory() as db:
        assert not db.scalars(select(outbox.db.Notification)).all()


def test_status_changes_emit_subscribed_status_event(outbox):
    before, after = fixture_report(), fixture_report()
    before["findings"][0]["status"] = "open"
    after["findings"][0]["status"] = "investigating"
    assert "status" in {
        category for category, _ in outbox.notifications.event_changes(before, after)
    }


@pytest.mark.asyncio
async def test_delivery_acknowledgment_logs_once_and_correct_owner(outbox):
    owner, other = outbox.owner("owner", 555), outbox.owner("other", 666)
    project, _, _ = outbox.project(owner, watch=True)
    other_project, _, _ = outbox.project(other, watch=True)
    first = outbox.add(owner, project)
    outbox.add(other, other_project)
    await outbox.worker.deliver()
    assert len(outbox.sent) == 1 and outbox.sent[0]["chat_id"] == 555
    assert "TEST-ONLY-ADVISORY" in outbox.sent[0]["text"]
    with outbox.factory() as db:
        assert db.get(outbox.db.Notification, first).status == "delivered"
        logs = db.scalars(
            select(outbox.db.Delivery).where(
                outbox.db.Delivery.notification_id == first
            )
        ).all()
        assert len(logs) == 1 and logs[0].status == "delivered"
    await outbox.worker.deliver()
    assert len(outbox.sent) == 2 and outbox.sent[1]["chat_id"] == 666
    await outbox.worker.deliver()
    assert len(outbox.sent) == 2


@pytest.mark.asyncio
async def test_temporary_failure_retry_after_then_success(outbox):
    owner = outbox.owner(telegram_id=555)
    project, _, _ = outbox.project(owner, watch=True)
    identifier = outbox.add(owner, project)
    outbox.responses.append((429, {"ok": False, "parameters": {"retry_after": 31}}))
    await outbox.worker.deliver()
    with outbox.factory() as db:
        notification = db.get(outbox.db.Notification, identifier)
        assert notification.status == "retry" and notification.attempts == 1
        assert notification.run_at.replace(tzinfo=UTC) == INSTANT + timedelta(
            seconds=31
        )
    await outbox.worker.deliver()
    assert len(outbox.sent) == 1
    with outbox.factory.begin() as db:
        db.get(outbox.db.Notification, identifier).run_at = INSTANT - timedelta(
            seconds=1
        )
    await outbox.worker.deliver()
    with outbox.factory() as db:
        assert db.get(outbox.db.Notification, identifier).status == "delivered"
        assert db.get(outbox.db.Notification, identifier).attempts == 2
    assert len(outbox.sent) == 2


@pytest.mark.asyncio
async def test_permanent_delivery_error_and_attempt_cap(outbox):
    owner = outbox.owner(telegram_id=555)
    project, _, _ = outbox.project(owner, watch=True)
    identifier = outbox.add(owner, project)
    outbox.responses.append(
        (403, {"ok": False, "description": "Synthetic blocked chat"})
    )
    await outbox.worker.deliver()
    with outbox.factory() as db:
        assert db.get(outbox.db.Notification, identifier).status == "failed"
    second = outbox.add(owner, project)
    with outbox.factory.begin() as db:
        db.get(outbox.db.Notification, second).attempts = 4
    outbox.responses.append((503, {"ok": False}))
    await outbox.worker.deliver()
    with outbox.factory() as db:
        assert db.get(outbox.db.Notification, second).status == "failed"


@pytest.mark.asyncio
async def test_delivery_rechecks_quiet_hours_before_sending(outbox):
    owner = outbox.owner(telegram_id=555)
    project, _, _ = outbox.project(owner, watch=True)
    identifier = outbox.add(owner, project)
    with outbox.factory.begin() as db:
        user = db.get(outbox.db.User, owner.id)
        user.preferences = {
            **user.preferences,
            "timezone": "UTC",
            "quiet_start": "09:00",
            "quiet_end": "11:00",
        }
    await outbox.worker.deliver()
    assert not outbox.sent
    with outbox.factory() as db:
        notification = db.get(outbox.db.Notification, identifier)
        assert notification.status == "pending"
        assert notification.run_at.replace(tzinfo=UTC) == datetime(
            2026, 10, 10, 11, 0, tzinfo=UTC
        )


@pytest.mark.asyncio
async def test_unsubscribe_prevents_delivery_and_cancels_pending(outbox):
    owner = outbox.owner(telegram_id=555)
    project, _, _ = outbox.project(owner, watch=False)
    identifier = outbox.add(owner, project)
    await outbox.worker.deliver()
    assert not outbox.sent
    with outbox.factory() as db:
        assert db.get(outbox.db.Notification, identifier).status == "cancelled"


@pytest.mark.asyncio
@pytest.mark.parametrize("preferences", [{"categories": []}, {"minimum_priority": 99}])
async def test_changed_category_and_threshold_cancel_previously_queued_event(
    outbox, preferences
):
    owner = outbox.owner(telegram_id=555)
    project, _, _ = outbox.project(owner, watch=True)
    identifier = outbox.add(owner, project)
    with outbox.factory.begin() as db:
        user = db.get(outbox.db.User, owner.id)
        user.preferences = {**user.preferences, **preferences}
    await outbox.worker.deliver()
    assert not outbox.sent
    with outbox.factory() as db:
        assert db.get(outbox.db.Notification, identifier).status == "cancelled"


@pytest.mark.asyncio
async def test_digest_groups_only_same_owner_enabled_projects(outbox):
    owner, other = outbox.owner("owner", 555), outbox.owner("other", 666)
    first_project, _, _ = outbox.project(owner, watch=True)
    second_project, _, _ = outbox.project(owner, watch=True)
    disabled_project, _, _ = outbox.project(owner, watch=False)
    foreign_project, _, _ = outbox.project(other, watch=True)
    identifiers = [outbox.add(owner, first_project), outbox.add(owner, second_project)]
    disabled = outbox.add(owner, disabled_project)
    foreign = outbox.add(other, foreign_project)
    with outbox.factory.begin() as db:
        user = db.get(outbox.db.User, owner.id)
        user.preferences = {**user.preferences, "digest": True}
        db.get(outbox.db.Project, disabled_project.id).name = "DISABLED-PRIVATE-FIXTURE"
        db.get(outbox.db.Notification, disabled).payload = {
            "project_name": "DISABLED-PRIVATE-FIXTURE",
            "finding": fixture_report()["findings"][0],
        }
    await outbox.worker.deliver()
    assert len(outbox.sent) == 1 and outbox.sent[0]["chat_id"] == 555
    assert "DISABLED-PRIVATE-FIXTURE" not in outbox.sent[0]["text"]
    with outbox.factory() as db:
        assert all(
            db.get(outbox.db.Notification, identifier).status == "delivered"
            for identifier in identifiers
        )
        assert db.get(outbox.db.Notification, foreign).status == "pending"
        assert db.get(outbox.db.Notification, disabled).status in {
            "pending",
            "cancelled",
        }


@pytest.mark.asyncio
async def test_crashed_delivery_lease_is_recovered(outbox):
    owner = outbox.owner(telegram_id=555)
    project, _, _ = outbox.project(owner, watch=True)
    identifier = outbox.add(owner, project, status="sending")
    with outbox.factory.begin() as db:
        db.get(outbox.db.Notification, identifier).lease_until = INSTANT - timedelta(
            minutes=1
        )
    await outbox.worker.deliver()
    with outbox.factory() as db:
        assert db.get(outbox.db.Notification, identifier).status == "delivered"
    assert len(outbox.sent) == 1


@pytest.mark.asyncio
async def test_awaiting_link_is_reactivated_by_single_use_link(outbox):
    owner = outbox.owner()
    project, _, _ = outbox.project(owner, watch=True)
    identifier = outbox.add(owner, project)
    await outbox.worker.deliver()
    assert not outbox.sent
    with outbox.factory() as db:
        assert db.get(outbox.db.Notification, identifier).status == "awaiting_link"
    web = outbox.client(owner)
    code = web.post("/api/auth/telegram/link").json()["code"]
    response = outbox.client().post(
        "/api/bot/link",
        json={"telegram_id": 555, "code": code},
        headers={"X-Bot-Key": outbox.settings.bot_key},
    )
    assert response.status_code == 200
    with outbox.factory() as db:
        assert db.get(outbox.db.Notification, identifier).status in {"pending", "retry"}
        # Fixture now is earlier than API creation time; keep test deterministic.
        db.get(outbox.db.Notification, identifier).run_at = INSTANT - timedelta(
            seconds=1
        )
        db.commit()
    await outbox.worker.deliver()
    assert len(outbox.sent) == 1 and outbox.sent[0]["chat_id"] == 555


def test_message_html_escapes_private_project_and_advisory_text(outbox):
    notification = type(
        "FixtureNotification",
        (),
        {
            "payload": {
                "project_name": "<project> & private",
                "finding": {
                    "id": "<advisory>",
                    "package": "<pkg>",
                    "version": "1.0",
                    "priority": 50,
                },
            },
            "category": "new",
            "project_id": "11111111-1111-4111-8111-111111111111",
        },
    )()
    message = outbox.notifications.message_text(
        [notification], "https://paxveil.example"
    )
    assert "&lt;project&gt; &amp; private" in message
    assert "&lt;advisory&gt;" in message and "&lt;pkg&gt;" in message


@pytest.mark.asyncio
async def test_worker_scan_ingests_snapshots_and_persists_report_without_network(
    outbox, monkeypatch
):
    owner = outbox.owner()
    _project, scan, job = outbox.project(owner)
    service = importlib.import_module("paxveil.core.service")

    async def controlled_scan(*args, **kwargs):
        return fixture_report()

    monkeypatch.setattr(service, "scan", controlled_scan)
    claimed = outbox.worker.claim_job()
    assert claimed[0] == job.id
    await outbox.worker.execute(*claimed)
    with outbox.factory() as db:
        assert db.get(outbox.db.Job, job.id).status == "succeeded"
        saved = db.get(outbox.db.Scan, scan.id)
        assert (
            saved.status == "completed"
            and saved.report["findings"][0]["id"] == "TEST-ONLY-ADVISORY"
        )
        assert len(db.scalars(select(outbox.db.Package)).all()) == 1
        assert len(db.scalars(select(outbox.db.SourceSnapshot)).all()) == 1
        assert len(db.scalars(select(outbox.db.Finding)).all()) == 1
        assert not db.scalars(
            select(outbox.db.Notification)
        ).all()  # baseline scan is not a fabricated alert


def test_crashed_job_lease_recovery_and_scheduler_deduplicate(outbox):
    owner = outbox.owner()
    project, scan, job = outbox.project(owner, watch=True)
    with outbox.factory.begin() as db:
        previous = db.get(outbox.db.Job, job.id)
        previous.status = "running"
        previous.lease_until = INSTANT - timedelta(minutes=1)
        previous.run_at = INSTANT - timedelta(seconds=1)
        db.get(outbox.db.Subscription, project.id).next_check = INSTANT - timedelta(
            minutes=1
        )
    assert outbox.worker.claim_job()[0] == job.id
    outbox.worker.schedule()
    with outbox.factory() as db:
        assert len(db.scalars(select(outbox.db.Job)).all()) == 1
        assert db.get(outbox.db.Scan, scan.id).status == "running"


@pytest.mark.asyncio
async def test_reclaimed_job_rejects_stale_worker_result(outbox, monkeypatch):
    owner = outbox.owner()
    _, scan, job = outbox.project(owner)
    service = importlib.import_module("paxveil.core.service")

    async def controlled_scan(*args, **kwargs):
        return fixture_report()

    monkeypatch.setattr(service, "scan", controlled_scan)
    first = outbox.worker.claim_job()
    with outbox.factory.begin() as db:
        db.get(outbox.db.Job, job.id).lease_until = INSTANT - timedelta(minutes=1)
    second = outbox.worker.claim_job()
    assert first[0] == second[0] and first[1] != second[1]
    await outbox.worker.execute(*first)
    with outbox.factory() as db:
        assert db.get(outbox.db.Job, job.id).status == "running"
        assert db.get(outbox.db.Scan, scan.id).report is None
    await outbox.worker.execute(*second)
    with outbox.factory() as db:
        assert db.get(outbox.db.Job, job.id).status == "succeeded"


@pytest.mark.asyncio
async def test_worker_retries_failure_then_fails_at_cap_without_secret_logs(
    outbox, monkeypatch
):
    owner = outbox.owner()
    _, scan, job = outbox.project(owner)
    service = importlib.import_module("paxveil.core.service")

    async def failed_source(*args, **kwargs):
        raise ValueError("secret-private-source-data")

    monkeypatch.setattr(service, "scan", failed_source)
    first = outbox.worker.claim_job()
    await outbox.worker.execute(*first)
    with outbox.factory.begin() as db:
        failed = db.get(outbox.db.Job, job.id)
        assert failed.status == "retry"
        assert "secret" not in failed.error
        failed.run_at = INSTANT - timedelta(seconds=1)
        failed.attempts = 2
    last = outbox.worker.claim_job()
    await outbox.worker.execute(*last)
    with outbox.factory() as db:
        assert db.get(outbox.db.Job, job.id).status == "failed"
        assert db.get(outbox.db.Scan, scan.id).status == "failed"


@pytest.mark.asyncio
async def test_enabling_digest_reschedules_immediate_queued_alert(outbox, monkeypatch):
    owner = outbox.owner(telegram_id=555)
    project, _, _ = outbox.project(owner, watch=True)
    identifier = outbox.add(owner, project)
    monkeypatch.setattr(outbox.api, "now", lambda: INSTANT)
    response = outbox.client(owner).put(
        "/api/settings", json={"timezone": "UTC", "digest": True}
    )
    assert response.status_code == 200
    with outbox.factory() as db:
        notification = db.get(outbox.db.Notification, identifier)
        assert notification.run_at.replace(tzinfo=UTC) == datetime(
            2026, 10, 11, 9, 0, tzinfo=UTC
        )
    await outbox.worker.deliver()
    assert not outbox.sent


@pytest.mark.asyncio
async def test_digest_timezone_change_reschedules_existing_digest(outbox, monkeypatch):
    owner = outbox.owner(telegram_id=555)
    project, _, _ = outbox.project(owner, watch=True)
    identifier = outbox.add(owner, project)
    with outbox.factory.begin() as db:
        user = db.get(outbox.db.User, owner.id)
        user.preferences = {**user.preferences, "timezone": "UTC", "digest": True}
        db.get(outbox.db.Notification, identifier).run_at = datetime(
            2026, 10, 11, 9, 0, tzinfo=UTC
        )
    monkeypatch.setattr(outbox.api, "now", lambda: INSTANT)
    response = outbox.client(owner).put(
        "/api/settings", json={"timezone": "Europe/Moscow", "digest": True}
    )
    assert response.status_code == 200
    with outbox.factory() as db:
        notification = db.get(outbox.db.Notification, identifier)
        assert notification.run_at.replace(tzinfo=UTC) == datetime(
            2026, 10, 11, 6, 0, tzinfo=UTC
        )
    await outbox.worker.deliver()
    assert not outbox.sent


@pytest.mark.asyncio
@pytest.mark.parametrize("baseline_status", ["ok", "cached", None, "flag_incomplete"])
async def test_osv_outage_recovery_does_not_republish_known_baseline_as_new(
    outbox, monkeypatch, baseline_status
):
    owner = outbox.owner(telegram_id=555)
    baseline = fixture_report()
    source_status = (
        "ok"
        if baseline_status == "flag_incomplete"
        else baseline_status or "unavailable"
    )
    baseline["sources"] = [{"name": "OSV", "status": source_status}]
    if baseline_status in {None, "flag_incomplete"}:
        baseline["findings"] = []
        baseline["completeness"] = "partial"
    if baseline_status == "flag_incomplete":
        baseline["vulnerability_lookup_complete"] = False
    recovered = fixture_report()
    project, baseline_scan, _ = outbox.project(owner, report=baseline, watch=True)
    with outbox.factory.begin() as db:
        db.get(outbox.db.Scan, baseline_scan.id).created_at = INSTANT - timedelta(
            minutes=30
        )
        outage = copy.deepcopy(baseline)
        outage["sources"] = [{"name": "OSV", "status": "unavailable"}]
        outage["findings"] = []
        outage["completeness"] = "partial"
        db.add(
            outbox.db.Scan(
                project_id=project.id,
                status="partial",
                report=outage,
                created_at=INSTANT - timedelta(minutes=20),
            )
        )
        recovery_scan = outbox.db.Scan(
            project_id=project.id, created_at=INSTANT - timedelta(minutes=10)
        )
        db.add(recovery_scan)
        db.flush()
        recovery_job = outbox.db.Job(
            user_id=owner.id,
            project_id=project.id,
            scan_id=recovery_scan.id,
            kind="scan",
            run_at=INSTANT - timedelta(seconds=1),
        )
        db.add(recovery_job)
        db.flush()
        recovery_id = recovery_job.id
    core = importlib.import_module("paxveil.core.service")

    async def controlled_recovery(*args, **kwargs):
        return copy.deepcopy(recovered)

    monkeypatch.setattr(core, "scan", controlled_recovery)
    claimed = outbox.worker.claim_job()
    assert claimed[0] == recovery_id
    await outbox.worker.execute(*claimed)
    with outbox.factory() as db:
        assert db.get(outbox.db.Job, recovery_id).status == "succeeded"
        assert not db.scalars(select(outbox.db.Notification)).all()


@pytest.mark.parametrize("incomplete_side", ["previous", "current"])
def test_lookup_complete_false_prevents_publishing_notifications(
    outbox, incomplete_side
):
    owner = outbox.owner(telegram_id=555)
    project, _, _ = outbox.project(owner, watch=True)
    previous, current = fixture_report(), fixture_report()
    current["findings"][0]["id"] = "TEST-ONLY-NEW-ADVISORY"
    selected = previous if incomplete_side == "previous" else current
    selected["vulnerability_lookup_complete"] = False
    selected["completeness"] = "partial"
    with outbox.factory.begin() as db:
        outbox.notifications.schedule_events(
            db,
            db.get(outbox.db.Project, project.id),
            db.get(outbox.db.User, owner.id),
            previous,
            current,
        )
    with outbox.factory() as db:
        assert not db.scalars(select(outbox.db.Notification)).all()


def test_advisory_baseline_skips_failed_json_null_reports(outbox):
    owner = outbox.owner()
    project, completed, _ = outbox.project(owner, report=fixture_report())
    with outbox.factory.begin() as db:
        db.get(outbox.db.Scan, completed.id).created_at = INSTANT - timedelta(
            minutes=30
        )
        db.add(
            outbox.db.Scan(
                project_id=project.id,
                status="failed",
                report=None,
                created_at=INSTANT - timedelta(minutes=20),
            )
        )
        current = outbox.db.Scan(
            project_id=project.id,
            status="queued",
            report=None,
            created_at=INSTANT - timedelta(minutes=10),
        )
        db.add(current)
        db.flush()
        current_id = current.id
    with outbox.factory() as db:
        baseline = outbox.worker.advisory_baseline(db, project.id, current_id)
        assert baseline is not None and baseline.id == completed.id


def test_shared_cve_alias_does_not_publish_same_vulnerability_as_new(outbox):
    previous, current = fixture_report(), fixture_report()
    previous["findings"][0].update(id="TEST-ONLY-FIRST-ID", aliases=["CVE-2099-10001"])
    current["findings"][0].update(id="TEST-ONLY-OTHER-ID", aliases=["CVE-2099-10001"])
    assert not list(outbox.notifications.event_changes(previous, current))


def test_alias_identity_deduplicates_persisted_notification_keys(outbox):
    owner = outbox.owner(telegram_id=555)
    project, _, _ = outbox.project(owner, watch=True)
    first, alternate = fixture_report(), fixture_report()
    first["findings"][0].update(id="TEST-ONLY-FIRST-ID", aliases=["CVE-2099-10001"])
    alternate["findings"][0].update(id="TEST-ONLY-OTHER-ID", aliases=["CVE-2099-10001"])
    with outbox.factory.begin() as db:
        user, item = (
            db.get(outbox.db.User, owner.id),
            db.get(outbox.db.Project, project.id),
        )
        outbox.notifications.schedule_events(db, item, user, {"findings": []}, first)
        outbox.notifications.schedule_events(
            db, item, user, {"findings": []}, alternate
        )
    with outbox.factory() as db:
        assert len(db.scalars(select(outbox.db.Notification)).all()) == 1


@pytest.mark.asyncio
async def test_stale_failed_scan_cannot_overwrite_successful_successor(
    outbox, monkeypatch
):
    owner = outbox.owner()
    _, scan, job = outbox.project(owner)
    core = importlib.import_module("paxveil.core.service")
    stale_started, finish_stale = asyncio.Event(), asyncio.Event()
    calls = 0

    async def controlled_scan(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            stale_started.set()
            await finish_stale.wait()
            raise ValueError("Synthetic late source failure")
        return fixture_report()

    monkeypatch.setattr(core, "scan", controlled_scan)
    first = outbox.worker.claim_job()
    stale = asyncio.create_task(outbox.worker.execute(*first))
    await asyncio.wait_for(stale_started.wait(), timeout=2)
    try:
        with outbox.factory.begin() as db:
            db.get(outbox.db.Job, job.id).lease_until = INSTANT - timedelta(minutes=1)
        second = outbox.worker.claim_job()
        assert first[1] != second[1]
        await outbox.worker.execute(*second)
        finish_stale.set()
        await stale
        with outbox.factory() as db:
            saved = db.get(outbox.db.Job, job.id)
            assert saved.status == "succeeded" and saved.claim_token == second[1]
            assert (
                saved.error is None
                and saved.result["findings"][0]["id"] == "TEST-ONLY-ADVISORY"
            )
            assert db.get(outbox.db.Scan, scan.id).status == "completed"
            assert db.get(outbox.db.Scan, scan.id).error is None
    finally:
        finish_stale.set()
        await stale


@pytest.mark.asyncio
@pytest.mark.parametrize("old_acknowledged", [True, False])
async def test_stale_telegram_delivery_cannot_finalize_successor_lease(
    outbox, monkeypatch, old_acknowledged
):
    owner = outbox.owner(telegram_id=555)
    project, _, _ = outbox.project(owner, watch=True)
    identifier = outbox.add(owner, project)
    started = [asyncio.Event(), asyncio.Event()]
    released = [asyncio.Event(), asyncio.Event()]
    calls = []

    async def controlled_transport(request):
        index = len(calls)
        calls.append(json.loads(request.content))
        started[index].set()
        await released[index].wait()
        if index == 0 and not old_acknowledged:
            return httpx.Response(
                429, json={"ok": False, "parameters": {"retry_after": 31}}
            )
        return httpx.Response(
            200, json={"ok": True, "result": {"message_id": index + 1}}
        )

    monkeypatch.setattr(
        outbox.worker.httpx,
        "AsyncClient",
        lambda **kwargs: outbox.http_client(
            transport=httpx.MockTransport(controlled_transport), **kwargs
        ),
    )
    first = asyncio.create_task(outbox.worker.deliver())
    second = None
    await asyncio.wait_for(started[0].wait(), timeout=2)
    try:
        with outbox.factory.begin() as db:
            db.get(outbox.db.Notification, identifier).lease_until = (
                INSTANT - timedelta(minutes=1)
            )
        second = asyncio.create_task(outbox.worker.deliver())
        await asyncio.wait_for(started[1].wait(), timeout=2)
        with outbox.factory() as db:
            newer = db.get(outbox.db.Notification, identifier)
            successor_claim = newer.claim_token
            successor_lease = newer.lease_until
            assert successor_claim is not None and newer.attempts == 2
        released[0].set()
        await first
        with outbox.factory() as db:
            newer = db.get(outbox.db.Notification, identifier)
            assert newer.status == "sending" and newer.claim_token == successor_claim
            assert newer.lease_until == successor_lease
            assert not db.scalars(select(outbox.db.Delivery)).all()
        released[1].set()
        await second
        with outbox.factory() as db:
            assert db.get(outbox.db.Notification, identifier).status == "delivered"
            logs = db.scalars(select(outbox.db.Delivery)).all()
            assert len(logs) == 1 and logs[0].status == "delivered"
    finally:
        for gate in released:
            gate.set()
        await asyncio.gather(first, *([second] if second else []))
