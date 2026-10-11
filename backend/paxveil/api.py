import copy
import re
import secrets
import time
from collections import OrderedDict
from datetime import timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from paxveil import __version__
from paxveil.auth import (
    bot_access,
    current_user,
    digest,
    new_session,
    password_hash,
    token_from,
    user_json,
    verify_password,
)
from paxveil.config import get_settings
from paxveil.db import (
    FindingState,
    Job,
    LinkCode,
    Notification,
    Project,
    Scan,
    Session,
    SessionLocal,
    StatusHistory,
    Subscription,
    User,
    get_db,
    now,
)
from paxveil.upload_limit import UploadLimitMiddleware

app = FastAPI(title="PAXVEIL API", version=__version__)
settings = get_settings()
origins = settings.allowed_origins.split(",")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type", "Authorization"])
limits: OrderedDict[str, tuple[float, int]] = OrderedDict()
app.add_middleware(UploadLimitMiddleware, max_bytes=settings.max_file_bytes + 16384)


@app.middleware("http")
async def security(request: Request, call_next):
    started = time.perf_counter()
    ip = request.client.host if request.client else "unknown"
    auth_route = request.url.path.startswith("/api/auth/")
    key = f"{ip}:{'auth' if auth_route else 'api'}"
    token = token_from(request)
    if token and not auth_route:
        with SessionLocal() as limit_db:
            owner = limit_db.scalar(select(Session.user_id).where(Session.token_hash == digest(token), Session.expires_at > now()))
        if owner:
            key = f"account:{owner}"
    window, count = limits.get(key, (time.monotonic(), 0))
    if time.monotonic() - window > 60:
        window, count = time.monotonic(), 0
    count += 1
    limits[key] = (window, count)
    limits.move_to_end(key)
    while len(limits) > 10000:
        limits.popitem(last=False)
    if count > (30 if auth_route else 240):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Слишком много запросов; повторите через минуту"}, status_code=429, headers={"Retry-After": "60"})
    if request.method in {"POST", "PUT", "DELETE"}:
        origin = request.headers.get("origin")
        if origin and origin not in origins:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Origin is not permitted"}, status_code=403)
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > settings.max_file_bytes + 16384):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Максимальный размер файла — 1 МБ"}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Server-Timing"] = f"app;dur={(time.perf_counter()-started)*1000:.2f}"
    return response


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=128)


class Preferences(BaseModel):
    timezone: str = "Europe/Moscow"
    quiet_start: str | None = None
    quiet_end: str | None = None
    minimum_priority: int = Field(default=0, ge=0, le=100)
    digest: bool = False
    categories: list[Literal["new", "priority", "fix", "exploitation", "status"]] = ["new", "priority", "fix", "exploitation", "status"]

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown IANA timezone") from None
        return value

    @field_validator("quiet_start", "quiet_end")
    @classmethod
    def valid_time(cls, value):
        if value is not None and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("Use HH:MM")
        return value


class WatchBody(BaseModel):
    enabled: bool


class FireBody(BaseModel):
    cve: str = Field(pattern=r"^CVE-\d{4}-\d{4,10}$")


class BotIdentity(BaseModel):
    telegram_id: int = Field(gt=0, le=2**63-1)


class BotLink(BotIdentity):
    code: str = Field(min_length=20, max_length=100)


class StateBody(BaseModel):
    advisory_id: str = Field(max_length=100)
    package: str = Field(max_length=200)
    status: Literal["open", "investigating", "accepted", "resolved"]


def owned_project(db, identifier, user):
    project = db.scalar(select(Project).where(Project.id == identifier, Project.user_id == user.id))
    if not project:
        raise HTTPException(404, "Проект не найден")
    return project


def owned_scan(db, identifier, user):
    scan = db.scalar(select(Scan).join(Project).where(Scan.id == identifier, Project.user_id == user.id))
    if not scan:
        raise HTTPException(404, "Анализ не найден")
    return scan


def scan_json(scan: Scan | None):
    if not scan:
        return None
    return {"id": scan.id, "status": scan.status, "report": scan.report, "error": scan.error, "created_at": scan.created_at}


def project_json(db, project):
    last = db.scalar(select(Scan).where(Scan.project_id == project.id).order_by(Scan.created_at.desc()).limit(1))
    watch = db.get(Subscription, project.id)
    latest = scan_json(last)
    if latest and latest["report"]:
        latest["report"] = copy.deepcopy(latest["report"])
        states = {(s.advisory_id, s.package): s.status for s in db.scalars(select(FindingState).where(FindingState.project_id == project.id))}
        for finding in latest["report"].get("findings", []):
            finding["status"] = states.get((finding["id"], finding["package"]), finding.get("status", "open"))
    return {"id": project.id, "name": project.name, "filename": project.filename, "python_version": project.python_version, "platform": project.platform, "created_at": project.created_at, "watch": bool(watch and watch.enabled), "latest_scan": latest}


def enqueue_scan(db, project):
    # Project row is the serialization lock for concurrent requests/scheduler.
    db.execute(select(Project).where(Project.id == project.id).with_for_update()).scalar_one()
    existing = db.scalar(select(Job).where(Job.project_id == project.id, Job.kind == "scan", Job.status.in_(["pending", "running", "retry"])))
    if existing:
        return existing
    scan = Scan(project_id=project.id)
    db.add(scan)
    db.flush()
    job = Job(user_id=project.user_id, project_id=project.id, scan_id=scan.id, kind="scan")
    db.add(job)
    db.flush()
    return job


@app.get("/api/health")
def health(db: DBSession = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": db.bind.dialect.name, "version": __version__}


@app.post("/api/auth/register", status_code=201)
def register(body: Credentials, response: Response, db: DBSession = Depends(get_db)):
    if not settings.registration_enabled:
        raise HTTPException(403, "Registration disabled")
    if body.username.lower().startswith("tg_"):
        raise HTTPException(422, "Reserved username prefix")
    user = User(username=body.username.lower(), password=password_hash(body.password), preferences=Preferences().model_dump())
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Имя пользователя уже занято") from None
    new_session(db, user, response)
    return user_json(user)


@app.post("/api/auth/login")
def login(body: Credentials, response: Response, db: DBSession = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username.lower()))
    if not verify_password(body.password, user.password if user else None):
        raise HTTPException(401, "Неверное имя пользователя или пароль")
    new_session(db, user, response)
    return user_json(user)


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return user_json(user)


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, db: DBSession = Depends(get_db)):
    token = token_from(request)
    if token:
        db.execute(delete(Session).where(Session.token_hash == digest(token)))
        db.commit()
    response.delete_cookie("paxveil_session", path="/")
    return {"ok": True}


@app.get("/api/projects")
def projects(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    return [project_json(db, p) for p in db.scalars(select(Project).where(Project.user_id == user.id).order_by(Project.created_at.desc()))]


@app.post("/api/projects", status_code=201)
async def create_project(name: str = Form(..., min_length=1, max_length=120), file: UploadFile = File(...), python_version: str = Form("3.11"), platform: str = Form("linux"), user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    if python_version not in [f"3.{v}" for v in range(9, 15)] or platform not in ["linux", "windows", "darwin"]:
        raise HTTPException(422, "Неподдерживаемая среда Python")
    filename = file.filename or ""
    if filename not in ["requirements.txt", "poetry.lock", "uv.lock"]:
        raise HTTPException(422, "Поддерживаются requirements.txt, poetry.lock и uv.lock")
    content = await file.read(settings.max_file_bytes + 1)
    await file.close()
    if not content or len(content) > settings.max_file_bytes:
        raise HTTPException(413, "Файл пуст или превышает 1 МБ")
    try:
        content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "Файл должен быть в UTF-8") from None
    from paxveil.core.parsers import parse
    try:
        parse(filename, content, python_version=python_version, platform=platform)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    project = Project(user_id=user.id, name=name.strip(), filename=filename, content=content, python_version=python_version, platform=platform)
    db.add(project)
    db.flush()
    enqueue_scan(db, project)
    db.commit()
    return project_json(db, project)


@app.get("/api/projects/{identifier}")
def project_detail(identifier: str, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    return project_json(db, owned_project(db, identifier, user))


@app.delete("/api/projects/{identifier}")
def delete_project(identifier: str, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    db.delete(owned_project(db, identifier, user))
    db.commit()
    return {"ok": True}


@app.post("/api/projects/{identifier}/scan")
def rescan(identifier: str, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    job = enqueue_scan(db, owned_project(db, identifier, user))
    db.commit()
    return {"id": job.id, "scan_id": job.scan_id, "status": job.status}


@app.get("/api/projects/{identifier}/scans")
def history(identifier: str, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    owned_project(db, identifier, user)
    return [scan_json(s) for s in db.scalars(select(Scan).where(Scan.project_id == identifier).order_by(Scan.created_at.desc()))]


@app.get("/api/scans/{identifier}")
def scan_detail(identifier: str, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    return scan_json(owned_scan(db, identifier, user))


@app.get("/api/jobs/{identifier}")
def job_detail(identifier: str, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    job = db.scalar(select(Job).where(Job.id == identifier, Job.user_id == user.id))
    if not job:
        raise HTTPException(404, "Задача не найдена")
    return {"id": job.id, "status": job.status, "kind": job.kind, "result": job.result, "error": job.error, "attempts": job.attempts}


@app.post("/api/scans/{identifier}/fixlab")
def fixlab(identifier: str, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    scan = owned_scan(db, identifier, user)
    if not scan.report:
        raise HTTPException(409, "Дождитесь результата анализа")
    db.execute(select(Project).where(Project.id == scan.project_id).with_for_update()).scalar_one()
    job = db.scalar(select(Job).where(Job.scan_id == scan.id, Job.kind == "fixlab", Job.status.in_(["pending", "running", "retry"])))
    if not job:
        job = Job(user_id=user.id, project_id=scan.project_id, scan_id=scan.id, kind="fixlab")
        db.add(job)
    db.commit()
    return {"id": job.id, "status": job.status}


@app.post("/api/fire")
async def fire_drill(body: FireBody, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    from paxveil.core.service import fire
    reports = []
    missing = []
    for project in db.scalars(select(Project).where(Project.user_id == user.id)):
        last = db.scalar(select(Scan).where(Scan.project_id == project.id, Scan.status.in_(["completed", "partial"]), Scan.report.is_not(None)).order_by(Scan.created_at.desc()).limit(1))
        if not last:
            missing.append(project.name)
        report = dict(last.report or {}) if last else {}
        report.update(project_id=project.id, project_name=project.name)
        reports.append(report)
    result = await fire(body.cve, reports)
    if missing:
        result.setdefault("limitations", []).append("Нет завершённого инвентаря для проектов: " + ", ".join(missing) + ". Их отсутствие в совпадениях не подтверждает, что они не затронуты.")
        if result.get("status") == "no_match":
            result["status"] = "insufficient_data"
    return result


@app.get("/api/settings")
def preferences(user: User = Depends(current_user)):
    return {**Preferences(**user.preferences).model_dump(), "telegram_id": int(user.telegram_id) if user.telegram_id else None}


@app.put("/api/settings")
def save_preferences(body: Preferences, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    if bool(body.quiet_start) != bool(body.quiet_end):
        raise HTTPException(422, "Укажите оба времени тихих часов")
    if body.quiet_start and body.quiet_start == body.quiet_end:
        raise HTTPException(422, "Начало и конец тихих часов должны отличаться")
    user.preferences = body.model_dump()
    from paxveil.notifications import delivery_time
    db.execute(update(Notification).where(Notification.user_id == user.id, Notification.status.in_(["pending", "retry", "awaiting_link"])).values(run_at=delivery_time(user.preferences, now())))
    db.commit()
    return {**body.model_dump(), "telegram_id": int(user.telegram_id) if user.telegram_id else None}


@app.put("/api/projects/{identifier}/watch")
def watch(identifier: str, body: WatchBody, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    owned_project(db, identifier, user)
    subscription = db.get(Subscription, identifier)
    if not subscription:
        subscription = Subscription(project_id=identifier)
        db.add(subscription)
    subscription.enabled = body.enabled
    subscription.next_check = now() + timedelta(seconds=settings.watch_interval_seconds)
    if not body.enabled:
        db.execute(update(Notification).where(Notification.project_id == identifier, Notification.status.in_(["pending", "retry", "sending"])).values(status="cancelled"))
    db.commit()
    return {"enabled": body.enabled}


@app.get("/api/notifications")
def notifications(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    return [{"id": n.id, "project_id": n.project_id, "category": n.category, "payload": n.payload, "status": n.status, "created_at": n.created_at, "attempts": n.attempts} for n in db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(200))]


@app.put("/api/projects/{identifier}/finding-status")
def finding_status(identifier: str, body: StateBody, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    owned_project(db, identifier, user)
    state = db.scalar(select(FindingState).where(FindingState.project_id == identifier, FindingState.advisory_id == body.advisory_id, FindingState.package == body.package))
    if not state:
        raise HTTPException(404, "Finding not found")
    if state.status != body.status:
        db.add(StatusHistory(state_id=state.id, old_status=state.status, new_status=body.status))
        subscription = db.get(Subscription, identifier)
        if subscription and subscription.enabled:
            from paxveil.notifications import schedule_events
            last = db.scalar(select(Scan).where(Scan.project_id == identifier, Scan.report.is_not(None)).order_by(Scan.created_at.desc()).limit(1))
            if last:
                finding = next((f for f in last.report.get("findings", []) if f["id"] == body.advisory_id and f["package"] == body.package), None)
                if finding:
                    before = {**finding, "status": state.status}
                    after = {**finding, "status": body.status, "status_changed_at": now().isoformat()}
                    schedule_events(db, owned_project(db, identifier, user), user, {"findings": [before]}, {"findings": [after]})
        state.status = body.status
    db.commit()
    return {"status": state.status}


@app.post("/api/auth/telegram/link")
def link_code(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    db.execute(select(User).where(User.id == user.id).with_for_update()).scalar_one()
    code = secrets.token_urlsafe(24)
    expires = now() + timedelta(minutes=10)
    db.execute(delete(LinkCode).where(LinkCode.user_id == user.id))
    db.add(LinkCode(code_hash=digest(code), user_id=user.id, expires_at=expires))
    db.commit()
    return {"code": code, "expires_at": expires}


@app.post("/api/bot/identity", dependencies=[Depends(bot_access)])
def bot_identity(body: BotIdentity, db: DBSession = Depends(get_db)):
    user = db.scalar(select(User).where(User.telegram_id == str(body.telegram_id)))
    if not user:
        user = User(username=f"tg_{body.telegram_id}", telegram_id=str(body.telegram_id), preferences=Preferences().model_dump())
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            user = db.scalar(select(User).where(User.telegram_id == str(body.telegram_id)))
    return {"token": new_session(db, user), "user": user_json(user)}


@app.post("/api/bot/link", dependencies=[Depends(bot_access)])
def bot_link(body: BotLink, db: DBSession = Depends(get_db)):
    link = db.scalar(select(LinkCode).where(LinkCode.code_hash == digest(body.code), LinkCode.expires_at > now()))
    if not link:
        raise HTTPException(400, "Код недействителен или истёк")
    target = db.scalar(select(User).where(User.id == link.user_id).with_for_update())
    link = db.scalar(select(LinkCode).where(LinkCode.code_hash == digest(body.code), LinkCode.expires_at > now()).with_for_update())
    if not link:
        raise HTTPException(400, "Код недействителен или истёк")
    if target.telegram_id and target.telegram_id != str(body.telegram_id):
        raise HTTPException(409, "Аккаунт уже связан с Telegram")
    previous = db.scalar(select(User).where(User.telegram_id == str(body.telegram_id)).with_for_update())
    if previous and previous.id != target.id:
        if previous.password:
            raise HTTPException(409, "Telegram связан с другим веб-аккаунтом")
        for cls in [Project, Job, Notification]:
            db.execute(update(cls).where(cls.user_id == previous.id).values(user_id=target.id))
        db.delete(previous)
        db.flush()
    target.telegram_id = str(body.telegram_id)
    db.execute(update(Notification).where(Notification.user_id == target.id, Notification.status == "awaiting_link").values(status="pending", run_at=now()))
    db.delete(link)
    db.commit()
    return {"token": new_session(db, target), "user": user_json(target)}
