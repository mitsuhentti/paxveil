"""Owner-scoped API security tests on isolated temporary SQLite databases."""

from __future__ import annotations

import importlib
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def api_env(tmp_path, monkeypatch):
    # Configure before importing db/api: never initialize or connect the runtime DB.
    test_url = "sqlite:///" + (tmp_path / "api-fixtures.sqlite").as_posix()
    monkeypatch.setenv("DATABASE_URL", test_url)
    monkeypatch.setenv("PAXVEIL_BOT_KEY", "synthetic-api-service-key")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    config = importlib.import_module("paxveil.config")
    config.get_settings.cache_clear()
    settings = config.get_settings()
    dbm = importlib.import_module("paxveil.db")
    auth = importlib.import_module("paxveil.auth")
    api = importlib.import_module("paxveil.api")
    engine = dbm.make_engine(test_url)
    dbm.Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(api, "settings", settings)
    api.limits.clear()

    def override_db():
        with factory() as db:
            yield db

    api.app.dependency_overrides[dbm.get_db] = override_db
    clients = []

    def client(user=None):
        headers = {}
        if user:
            with factory() as db:
                owner = db.get(dbm.User, user.id)
                headers = {"Authorization": "Bearer " + auth.new_session(db, owner)}
        instance = TestClient(api.app, headers=headers)
        clients.append(instance)
        return instance

    def owner(username="fixture_owner", telegram_id=None, *, web=True):
        with factory.begin() as db:
            user = dbm.User(
                username=username,
                telegram_id=str(telegram_id) if telegram_id else None,
                password=auth.password_hash("synthetic-password-1234") if web else None,
                preferences=api.Preferences().model_dump(),
            )
            db.add(user)
            db.flush()
            return user

    def project(user, *, report=None, watch=False, run_at=None):
        with factory.begin() as db:
            item = dbm.Project(
                user_id=user.id,
                name="Synthetic fixture project",
                filename="requirements.txt",
                content=b"fixture-package==1.0\n",
            )
            db.add(item)
            db.flush()
            scan = dbm.Scan(
                project_id=item.id,
                status="completed" if report else "queued",
                report=report,
            )
            db.add(scan)
            db.flush()
            job = dbm.Job(
                user_id=user.id,
                project_id=item.id,
                scan_id=scan.id,
                kind="scan",
                status="succeeded" if report else "pending",
                run_at=run_at,
            )
            db.add(job)
            db.add(dbm.Subscription(project_id=item.id, enabled=watch))
            db.flush()
            return item, scan, job

    yield SimpleNamespace(
        api=api,
        auth=auth,
        db=dbm,
        factory=factory,
        engine=engine,
        settings=settings,
        owner=owner,
        project=project,
        client=client,
    )
    for instance in clients:
        instance.close()
    api.app.dependency_overrides.clear()
    api.limits.clear()
    engine.dispose()
    config.get_settings.cache_clear()


def fixture_report(priority=80):
    return {
        "dependencies": [
            {
                "name": "fixture-package",
                "version": "1.0",
                "direct": True,
                "source": "test",
            }
        ],
        "findings": [
            {
                "id": "TEST-ONLY-ADVISORY",
                "aliases": [],
                "package": "fixture-package",
                "version": "1.0",
                "severity": "high",
                "priority": priority,
                "summary": "Controlled fixture only",
                "fixed_versions": [],
                "kev": False,
            }
        ],
        "sources": [{"name": "OSV", "status": "ok", "test_fixture": True}],
        "completeness": "complete",
        "stats": {"dependencies": 1, "findings": 1},
    }


def test_anonymous_denied_and_secure_cookie_login_logout(api_env):
    client = api_env.client()
    assert client.get("/api/projects").status_code == 401
    credentials = {"username": "web_fixture", "password": "synthetic-password-1234"}
    response = client.post("/api/auth/register", json=credentials)
    assert response.status_code == 201
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert client.get("/api/auth/me").json()["username"] == "web_fixture"
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.post(
            "/api/auth/login",
            json={**credentials, "password": "synthetic-wrong-password"},
        ).status_code
        == 401
    )
    assert client.post("/api/auth/login", json=credentials).status_code == 200


def test_username_prefix_and_password_requirements(api_env):
    client = api_env.client()
    assert (
        client.post(
            "/api/auth/register",
            json={"username": "tg_99", "password": "synthetic-password-1234"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/auth/register",
            json={"username": "short_password", "password": "short"},
        ).status_code
        == 422
    )


def test_expired_and_logged_out_bearer_cannot_be_used(api_env):
    user = api_env.owner()
    with api_env.factory() as db:
        token = api_env.auth.new_session(db, user)
        session = db.get(api_env.db.Session, api_env.auth.digest(token))
        session.expires_at = api_env.db.now() - timedelta(seconds=1)
        db.commit()
    client = api_env.client()
    client.headers["Authorization"] = "Bearer " + token
    assert client.get("/api/projects").status_code == 401
    active = api_env.client(user)
    assert active.post("/api/auth/logout").status_code == 200
    assert active.get("/api/projects").status_code == 401


def test_every_project_scan_job_mutation_is_owner_scoped(api_env):
    alice, bob = api_env.owner("alice"), api_env.owner("bob")
    project, scan, job = api_env.project(alice, report=fixture_report(), watch=True)
    with api_env.factory.begin() as db:
        db.add(
            api_env.db.FindingState(
                project_id=project.id,
                advisory_id="TEST-ONLY-ADVISORY",
                package="fixture-package",
            )
        )
    attacker = api_env.client(bob)
    calls = [
        ("get", f"/api/projects/{project.id}", {}),
        ("delete", f"/api/projects/{project.id}", {}),
        ("post", f"/api/projects/{project.id}/scan", {}),
        ("get", f"/api/projects/{project.id}/scans", {}),
        ("get", f"/api/scans/{scan.id}", {}),
        ("get", f"/api/jobs/{job.id}", {}),
        ("post", f"/api/scans/{scan.id}/fixlab", {}),
        ("put", f"/api/projects/{project.id}/watch", {"json": {"enabled": False}}),
        (
            "put",
            f"/api/projects/{project.id}/finding-status",
            {
                "json": {
                    "advisory_id": "TEST-ONLY-ADVISORY",
                    "package": "fixture-package",
                    "status": "resolved",
                }
            },
        ),
    ]
    for method, path, kwargs in calls:
        response = getattr(attacker, method)(path, **kwargs)
        assert response.status_code == 404, (method, path, response.text)
    assert attacker.get("/api/projects").json() == []
    with api_env.factory() as db:
        assert db.get(api_env.db.Project, project.id) is not None
        assert db.get(api_env.db.Subscription, project.id).enabled


def test_fire_receives_only_callers_saved_reports(api_env, monkeypatch):
    owner, other = api_env.owner(), api_env.owner("other_owner")
    mine, _, _ = api_env.project(owner, report=fixture_report())
    theirs, _, _ = api_env.project(other, report=fixture_report())
    captured = []

    async def controlled_fire(cve, reports):
        captured.extend(reports)
        return {
            "cve": cve,
            "status": "fixture",
            "matches": [],
            "limitations": ["Test transport"],
        }

    service = importlib.import_module("paxveil.core.service")
    monkeypatch.setattr(service, "fire", controlled_fire)
    client = api_env.client(owner)
    assert client.post("/api/fire", json={"cve": "CVE-2024-35195"}).status_code == 200
    assert {r["project_id"] for r in captured} == {mine.id}
    assert theirs.id not in {r["project_id"] for r in captured}
    assert client.post("/api/fire", json={"cve": "../../etc/passwd"}).status_code == 422


@pytest.mark.parametrize(
    "filename,content,status",
    [
        ("../requirements.txt", b"requests==2.19.1", 422),
        ("script.py", b"print('must never run')", 422),
        ("requirements.txt", b"", 413),
        ("requirements.txt", b"\xff\xfe", 422),
        ("poetry.lock", b"[broken", 422),
        ("requirements.txt", b"requests==2.19.1", 201),
    ],
)
def test_upload_validates_format_filename_content(api_env, filename, content, status):
    client = api_env.client(api_env.owner())
    response = client.post(
        "/api/projects",
        data={"name": "Upload fixture"},
        files={"file": (filename, content)},
    )
    assert response.status_code == status, response.text
    if status != 201:
        assert client.get("/api/projects").json() == []
    else:
        assert response.json()["latest_scan"]["status"] == "queued"


def test_upload_size_and_environment_limits(api_env):
    client = api_env.client(api_env.owner())
    assert (
        client.post(
            "/api/projects",
            data={"name": "Too large"},
            files={"file": ("requirements.txt", b"x" * 1_048_577)},
        ).status_code
        == 413
    )
    assert (
        client.post(
            "/api/projects",
            data={"name": "Bad platform", "platform": "http://127.0.0.1"},
            files={"file": ("requirements.txt", b"requests==2.19.1")},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/projects",
            data={"name": "Bad Python", "python_version": "2.7"},
            files={"file": ("requirements.txt", b"requests==2.19.1")},
        ).status_code
        == 422
    )


@pytest.mark.asyncio
async def test_chunked_upload_without_content_length_is_bounded_before_persistence(
    api_env, monkeypatch
):
    """A small valid file cannot bypass the body cap through multipart padding."""
    monkeypatch.setattr(api_env.api, "SessionLocal", api_env.factory)
    owner = api_env.owner()
    authenticated = api_env.client(owner)
    boundary = "paxveil-streamed-fixture"
    body_limit = api_env.settings.max_file_bytes + 16_384
    padding = b"x" * (body_limit // 2 + 32_768)
    # Each padding field is below Starlette's per-part limit. The uploaded file
    # itself is also small and valid, so only the cumulative body cap rejects it.
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="name"\r\n\r\n'
        "Streamed fixture\r\n"
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
        'filename="requirements.txt"\r\nContent-Type: text/plain\r\n\r\n'
        "fixture-package==1.0\r\n"
        f'--{boundary}\r\nContent-Disposition: form-data; name="padding_a"\r\n\r\n'
    ).encode() + padding + (
        f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="padding_b"\r\n\r\n'
    ).encode() + padding + f"\r\n--{boundary}--\r\n".encode()
    streamed_bytes = 0

    async def stream():
        nonlocal streamed_bytes
        for offset in range(0, len(body), 65_536):
            chunk = body[offset : offset + 65_536]
            streamed_bytes += len(chunk)
            yield chunk

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api_env.api.app),
        base_url="http://testserver",
    ) as client:
        request = client.build_request(
            "POST",
            "/api/projects",
            content=stream(),
            headers={
                "Authorization": authenticated.headers["authorization"],
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        assert "content-length" not in request.headers
        assert request.headers["transfer-encoding"] == "chunked"
        response = await client.send(request)

    assert response.status_code == 413
    assert body_limit < streamed_bytes < len(body)
    with api_env.factory() as db:
        assert db.scalar(select(api_env.db.Project.id)) is None


def test_rescanning_deduplicates_active_job_and_delete_cascades(api_env):
    owner = api_env.owner()
    project, scan, job = api_env.project(owner, watch=True)
    client = api_env.client(owner)
    assert client.post(f"/api/projects/{project.id}/scan").json()["id"] == job.id
    assert client.post(f"/api/projects/{project.id}/scan").json()["id"] == job.id
    with api_env.factory() as db:
        assert len(db.scalars(select(api_env.db.Job)).all()) == 1
    assert client.delete(f"/api/projects/{project.id}").status_code == 200
    with api_env.factory() as db:
        assert db.get(api_env.db.Scan, scan.id) is None
        assert db.get(api_env.db.Job, job.id) is None
        assert db.get(api_env.db.Subscription, project.id) is None


def test_settings_reject_unknown_timezone_partial_and_equal_quiet_hours(api_env):
    client = api_env.client(api_env.owner())
    assert (
        client.put("/api/settings", json={"timezone": "Unknown/Fixture"}).status_code
        == 422
    )
    assert client.put("/api/settings", json={"quiet_start": "22:00"}).status_code == 422
    assert (
        client.put(
            "/api/settings", json={"quiet_start": "30:00", "quiet_end": "08:00"}
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/settings", json={"quiet_start": "09:00", "quiet_end": "09:00"}
        ).status_code
        == 422
    )


def test_untrusted_origin_write_is_blocked_and_security_headers_present(api_env):
    client = api_env.client(api_env.owner())
    assert (
        client.put(
            "/api/settings", json={}, headers={"Origin": "https://attacker.invalid"}
        ).status_code
        == 403
    )
    response = client.get("/api/projects")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"


def test_bot_identity_requires_service_key_not_client_supplied_id(api_env):
    client = api_env.client()
    assert (
        client.post("/api/bot/identity", json={"telegram_id": 555}).status_code == 403
    )
    assert (
        client.post(
            "/api/bot/identity",
            json={"telegram_id": 555},
            headers={"X-Bot-Key": "wrong"},
        ).status_code
        == 403
    )
    response = client.post(
        "/api/bot/identity",
        json={"telegram_id": 555},
        headers={"X-Bot-Key": api_env.settings.bot_key},
    )
    assert response.status_code == 200 and response.json()["user"]["telegram_id"] == 555


def test_link_code_consumed_merge_owner_sessions_and_jobs(api_env):
    web, telegram = api_env.owner("web_owner"), api_env.owner("tg_555", 555, web=False)
    project, scan, job = api_env.project(telegram, report=fixture_report(), watch=True)
    web_client, old_telegram_client = api_env.client(web), api_env.client(telegram)
    code = web_client.post("/api/auth/telegram/link").json()["code"]
    response = api_env.client().post(
        "/api/bot/link",
        json={"telegram_id": 555, "code": code},
        headers={"X-Bot-Key": api_env.settings.bot_key},
    )
    assert response.status_code == 200, response.text
    assert response.json()["user"]["id"] == web.id
    assert old_telegram_client.get("/api/projects").status_code == 401
    assert web_client.get(f"/api/projects/{project.id}").status_code == 200
    assert web_client.get(f"/api/jobs/{job.id}").status_code == 200
    assert (
        api_env.client()
        .post(
            "/api/bot/link",
            json={"telegram_id": 555, "code": code},
            headers={"X-Bot-Key": api_env.settings.bot_key},
        )
        .status_code
        == 400
    )
    with api_env.factory() as db:
        assert db.get(api_env.db.User, telegram.id) is None
        assert db.get(api_env.db.Project, project.id).user_id == web.id
        assert db.get(api_env.db.Job, job.id).user_id == web.id
        assert db.get(api_env.db.Subscription, project.id).enabled
        assert db.get(api_env.db.Scan, scan.id) is not None


def test_link_cannot_replace_other_web_owners_telegram(api_env):
    first, second = api_env.owner("first_web", 555), api_env.owner("second_web")
    second_client = api_env.client(second)
    code = second_client.post("/api/auth/telegram/link").json()["code"]
    response = api_env.client().post(
        "/api/bot/link",
        json={"telegram_id": 555, "code": code},
        headers={"X-Bot-Key": api_env.settings.bot_key},
    )
    assert response.status_code == 409
    with api_env.factory() as db:
        assert db.get(api_env.db.User, first.id).telegram_id == "555"
        assert db.get(api_env.db.User, second.id).telegram_id is None


def test_link_code_expiration_and_rotation(api_env):
    client = api_env.client(api_env.owner())
    old = client.post("/api/auth/telegram/link").json()["code"]
    new = client.post("/api/auth/telegram/link").json()["code"]
    bot = api_env.client()
    headers = {"X-Bot-Key": api_env.settings.bot_key}
    assert (
        bot.post(
            "/api/bot/link", json={"telegram_id": 555, "code": old}, headers=headers
        ).status_code
        == 400
    )
    with api_env.factory.begin() as db:
        record = db.get(api_env.db.LinkCode, api_env.auth.digest(new))
        record.expires_at = api_env.db.now() - timedelta(seconds=1)
    assert (
        bot.post(
            "/api/bot/link", json={"telegram_id": 555, "code": new}, headers=headers
        ).status_code
        == 400
    )


def test_notifications_owner_isolation_and_watch_disable_cancels_queue(api_env):
    alice, bob = api_env.owner("alice"), api_env.owner("bob")
    project, _, _ = api_env.project(alice, watch=True)
    with api_env.factory.begin() as db:
        notification = api_env.db.Notification(
            user_id=alice.id,
            project_id=project.id,
            event_key="synthetic-notification-key",
            category="new",
            payload={"finding": {}},
        )
        db.add(notification)
        db.flush()
        notification_id = notification.id
    assert api_env.client(bob).get("/api/notifications").json() == []
    alice_client = api_env.client(alice)
    assert alice_client.get("/api/notifications").json()[0]["id"] == notification_id
    assert (
        alice_client.put(
            f"/api/projects/{project.id}/watch", json={"enabled": False}
        ).status_code
        == 200
    )
    with api_env.factory() as db:
        assert db.get(api_env.db.Notification, notification_id).status == "cancelled"


@pytest.mark.parametrize("interrupted_status", ["queued", "running", "failed"])
def test_fire_keeps_last_completed_report_during_interrupted_rescan(
    api_env, monkeypatch, interrupted_status
):
    owner = api_env.owner()
    baseline = fixture_report()
    project, completed, _ = api_env.project(owner, report=baseline)
    with api_env.factory.begin() as db:
        db.get(api_env.db.Scan, completed.id).created_at = api_env.db.now() - timedelta(
            minutes=10
        )
        db.add(
            api_env.db.Scan(
                project_id=project.id,
                status=interrupted_status,
                report=None,
                created_at=api_env.db.now(),
            )
        )
    captured = []

    async def controlled_fire(cve, reports):
        captured.extend(reports)
        return {
            "cve": cve,
            "status": "synthetic fixture",
            "matches": [],
            "limitations": [],
        }

    core = importlib.import_module("paxveil.core.service")
    monkeypatch.setattr(core, "fire", controlled_fire)
    response = api_env.client(owner).post("/api/fire", json={"cve": "CVE-2024-35195"})
    assert response.status_code == 200
    assert len(captured) == 1
    assert captured[0]["project_id"] == project.id
    assert captured[0]["dependencies"] == baseline["dependencies"]
    assert captured[0]["findings"] == baseline["findings"]
