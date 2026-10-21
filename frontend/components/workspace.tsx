"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ArrowUpRight, Bell, Check, ChevronRight, Folder, History, LayoutGrid, LogOut, Menu, Plus, Radar, Search, Settings2, X } from "lucide-react";
import { Brand } from "./brand";
import { api, ApiError, formatDate, json } from "@/lib/api";
import type { Notification, Project, Scan, User } from "@/lib/types";
import { Empty, ErrorBanner, Loading, statusLabel } from "./ui";
import { Upload } from "./upload";
import { ProjectView } from "./project";
import { FireDrill } from "./fire";
import { Settings } from "./settings";

const navigation = [
  { path: "/app", label: "Проекты", icon: LayoutGrid },
  { path: "/app/watch", label: "Мониторинг", icon: Radar },
  { path: "/app/fire", label: "Проверка CVE", icon: Search },
  { path: "/app/history", label: "История", icon: History },
  { path: "/app/settings", label: "Настройки", icon: Settings2 },
];

export function Workspace() {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [upload, setUpload] = useState(false);
  const [mobile, setMobile] = useState(false);
  const [toast, setToast] = useState("");
  const sidebar = useRef<HTMLElement>(null);
  const menu = useRef<HTMLButtonElement>(null);
  const refresh = useCallback(() => {
    api<Project[]>("/projects").then(data => { setProjects(data); setError(""); }).catch((failure) => setError(failure.message));
  }, []);

  useEffect(() => {
    try {
      const theme = localStorage.getItem("paxveil-theme");
      if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
    } catch { /* The default theme works when browser storage is unavailable. */ }
    let alive = true;
    async function load() {
      try {
        const currentUser = await api<User>("/auth/me");
        if (!alive) return;
        setUser(currentUser);
        const data = await api<Project[]>("/projects");
        if (alive) setProjects(data);
      } catch (failure) {
        if (failure instanceof ApiError && failure.status === 401) router.replace("/login");
        else if (alive) setError(failure instanceof Error ? failure.message : "Не удалось загрузить проекты.");
      } finally {
        if (alive) setLoading(false);
      }
    }
    load();
    return () => { alive = false; };
  }, [router]);
  useEffect(() => { setMobile(false); setError(""); }, [pathname]);
  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 761px)");
    const closeOnDesktop = () => { if (desktop.matches) setMobile(false); };
    desktop.addEventListener("change", closeOnDesktop);
    return () => desktop.removeEventListener("change", closeOnDesktop);
  }, []);
  useEffect(() => {
    if (!mobile) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const controls = () => Array.from(sidebar.current?.querySelectorAll<HTMLElement>("a[href], button:not([disabled])") || [])
      .filter(element => element.offsetParent !== null);
    controls()[0]?.focus();
    function keydown(event: KeyboardEvent) {
      if (event.key === "Escape") { event.preventDefault(); setMobile(false); }
      if (event.key !== "Tab") return;
      const items = controls();
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    document.addEventListener("keydown", keydown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", keydown);
      menu.current?.focus();
    };
  }, [mobile]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 5000);
    return () => clearTimeout(timer);
  }, [toast]);
  useEffect(() => {
    if (!projects.some((project) => ["queued", "running"].includes(project.latest_scan?.status || ""))) return;
    const timer = setInterval(refresh, 4000);
    return () => clearInterval(timer);
  }, [projects, refresh]);

  async function logout() {
    try {
      await api("/auth/logout", { method: "POST" });
      if (user) { try { sessionStorage.removeItem(`paxveil-settings-draft:${user.id}`); } catch { /* Storage may be disabled. */ } }
      router.replace("/");
    }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Не удалось выйти."); }
  }

  const selected = pathname.match(/^\/app\/projects\/([^/]+)$/)?.[1];
  const section = selected ? "project" : pathname.split("/")[2] || "projects";
  const sectionLabel = navigation.find((item) => item.path === pathname)?.label || "Проект";
  const monitored = projects.filter((project) => project.watch).length;

  return (
    <div className="workspace">
      <a href="#main" className="skip-link">Перейти к содержимому</a>
      <aside ref={sidebar} id="workspace-sidebar" className={`sidebar ${mobile ? "mobile-open" : ""}`} role={mobile ? "dialog" : undefined} aria-modal={mobile || undefined} aria-label={mobile ? "Меню приложения" : undefined}>
        <div className="sidebar-brand"><Brand />
          <button className="mobile-close icon-button" onClick={() => setMobile(false)} aria-label="Закрыть меню"><X size={20} /></button>
        </div>
        <p className="nav-caption">Рабочая область</p>
        <nav aria-label="Разделы приложения">
          {navigation.map((item) => {
            const active = item.path === "/app" ? ["projects", "project"].includes(section) : pathname === item.path;
            return (
              <Link href={item.path} key={item.path} className={active ? "active" : ""} aria-current={active ? "page" : undefined} onClick={() => setMobile(false)}>
                <item.icon size={18} strokeWidth={1.7} /><span>{item.label}</span>
                {item.path === "/app/watch" && monitored > 0 && <small>{monitored}</small>}
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <Link className="workspace-label" href="/app/settings" onClick={() => setMobile(false)}>
            <span className="workspace-avatar">{user?.username.charAt(0).toUpperCase() || "P"}</span>
            <span><strong>{user?.username || "Аккаунт"}</strong><small>Настройки аккаунта</small></span>
          </Link>
          <button onClick={logout}><LogOut size={17} />Выйти</button>
        </div>
      </aside>
      {mobile && <button className="mobile-scrim" aria-label="Закрыть меню" onClick={() => setMobile(false)} />}
      <div className="workspace-body" inert={mobile}>
        <header className="topbar">
          <div>
            <button ref={menu} className="icon-button mobile-menu" aria-label="Открыть меню" aria-expanded={mobile} aria-controls="workspace-sidebar" onClick={() => setMobile(true)}><Menu size={21} /></button>
            <div className="breadcrumb"><Link href="/app">PAXVEIL</Link><ChevronRight size={14} /><span>{sectionLabel}</span></div>
          </div>
          <button className="button small secondary" onClick={() => setUpload(true)}><Plus size={16} />Новый проект</button>
        </header>
        <main id="main" className="workspace-main">
          {error && <ErrorBanner message={error} retry={() => window.location.reload()} />}
          {loading ? <Loading text="Загрузка проектов..." /> : !user ? (
            <Empty title="Не удалось подключиться" detail="Повторите загрузку страницы.">
              <button className="button primary" onClick={() => window.location.reload()}>Повторить</button>
            </Empty>
          ) : selected ? (
            <ProjectView key={selected} id={selected} changed={refresh} deleted={() => { refresh(); router.push("/app"); }} notify={setToast} />
          ) : section === "fire" ? <FireDrill hasProjects={projects.length > 0} create={() => setUpload(true)} />
            : section === "settings" ? <Settings user={user} notify={setToast} />
              : section === "watch" ? <Watch projects={projects} refresh={refresh} notify={setToast} create={() => setUpload(true)} />
                : section === "history" ? <GlobalHistory projects={projects} create={() => setUpload(true)} />
                  : <Dashboard projects={projects} create={() => setUpload(true)} />}
        </main>
      </div>
      <Upload open={upload} close={() => setUpload(false)} created={(project) => { refresh(); router.push(`/app/projects/${project.id}`); }} />
      {toast && <div role="status" className="toast"><Check size={17} />{toast}
        <button className="icon-button" onClick={() => setToast("")} aria-label="Закрыть уведомление"><X size={16} /></button>
      </div>}
    </div>
  );
}

function Dashboard({ projects, create }: { projects: Project[]; create: () => void }) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("recent");
  const filtered = projects.filter((project) => project.name.toLowerCase().includes(query.trim().toLowerCase()))
    .sort((left, right) => sort === "name" ? left.name.localeCompare(right.name) : new Date(right.created_at).getTime() - new Date(left.created_at).getTime());
  const reports = projects.filter((project) => project.latest_scan?.report);
  const findings = reports.reduce((sum, project) => sum + (project.latest_scan?.report?.stats.findings || 0), 0);
  const partialReports = reports.filter(project => !["complete", "recorded_versions_checked"].includes(project.latest_scan!.report!.completeness)).length;

  return (
    <section>
      <div className="page-heading"><div><h1>Проекты</h1><p>Зависимости, результаты проверок и обновления.</p></div>
        <button className="button primary" onClick={create}><Plus size={17} />Добавить проект</button>
      </div>
      <div className="dashboard-summary">
        <div><span>Всего проектов</span><strong>{projects.length}</strong></div>
        <div><span>Уязвимости</span><strong className={findings ? "text-danger" : ""}>{reports.length ? findings : "н/д"}</strong>
          <small>{reports.length ? `Последних отчётов: ${reports.length}${partialReports ? ` · неполных: ${partialReports}` : ""}` : "Нет готовых отчётов"}</small></div>
        <div><span>Мониторинг включён</span><strong>{projects.filter((project) => project.watch).length}</strong></div>
      </div>
      <div className="report-section">
        <div className="table-toolbar">
          <label className="search-box"><Search size={17} /><input aria-label="Поиск проектов" placeholder="Поиск по названию" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
          <select aria-label="Сортировка проектов" value={sort} onChange={(event) => setSort(event.target.value)}><option value="recent">Сначала новые</option><option value="name">По названию</option></select>
        </div>
        {projects.length ? filtered.length ? (
          <div className="project-registry">
            <div className="registry-head"><span>Проект</span><span>Последняя проверка</span><span>Пакеты</span><span>Уязвимости</span><span>Мониторинг</span><span /></div>
            {filtered.map((project) => (
              <Link className="project-row" href={`/app/projects/${project.id}`} key={project.id}>
                <div className="project-name"><span className="project-glyph"><Folder size={20} strokeWidth={1.7} /></span>
                  <div><strong>{project.name}</strong><small>{formatDate(project.latest_scan?.created_at)}</small>
                    <span className="mobile-project-stats"><span>Пакеты: {project.latest_scan?.report?.stats.dependencies ?? "н/д"}</span><span className={project.latest_scan?.report?.stats.findings ? "text-danger" : ""}>Уязвимости: {project.latest_scan?.report?.stats.findings ?? "н/д"}</span></span>
                  </div></div>
                <span className={`status-badge ${project.latest_scan?.status || "queued"}`}>{project.latest_scan ? statusLabel(project.latest_scan.status) : "Нет проверок"}</span>
                <span className="mono registry-number">{project.latest_scan?.report?.stats.dependencies ?? "н/д"}</span>
                <span className={`mono registry-number ${project.latest_scan?.report?.stats.findings ? "text-danger" : ""}`}>{project.latest_scan?.report?.stats.findings ?? "н/д"}</span>
                <span className={`watch-status ${project.watch ? "enabled" : ""}`}><span className={`status-dot ${project.watch ? "ok" : ""}`} />{project.watch ? "Включён" : "Выключен"}</span><ChevronRight size={17} />
              </Link>
            ))}
          </div>
        ) : <Empty title="Ничего не найдено" detail="Попробуйте другое название."><button className="button secondary" onClick={() => setQuery("")}>Сбросить поиск</button></Empty> : (
          <Empty title="Добавьте первый проект" detail="Загрузите requirements.txt, poetry.lock или uv.lock. Результат проверки будет сохранён здесь.">
            <button className="button primary" onClick={create}><Plus size={17} />Добавить проект</button>
          </Empty>
        )}
      </div>
    </section>
  );
}

function Watch({ projects, refresh, notify, create }: { projects: Project[]; refresh: () => void; notify: (text: string) => void; create: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    api<Notification[]>("/notifications").then((data) => { if (alive) setNotifications(data); })
      .catch((failure) => { if (alive) setError(failure.message); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);
  async function toggle(project: Project) {
    setBusy(project.id); setError("");
    try {
      const result = await api<{ enabled: boolean }>(`/projects/${project.id}/watch`, { method: "PUT", body: json({ enabled: !project.watch }) });
      refresh(); notify(result.enabled ? "Мониторинг включён" : "Мониторинг отключён");
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Не удалось изменить подписку."); }
    finally { setBusy(null); }
  }
  return (
    <section>
      <div className="page-heading"><div><h1>Мониторинг</h1><p>Повторные проверки проектов и уведомления об изменениях.</p></div></div>
      {error && <ErrorBanner message={error} />}
      <div className="watch-note"><Bell size={20} /><div><strong>Уведомления в Telegram</strong>
        <p>Подключите бота и выберите события в <Link href="/app/settings">настройках</Link>. Для регулярных проверок сервис должен оставаться запущенным.</p>
      </div></div>
      <div className="watch-projects">
        {projects.length ? projects.map((project) => (
          <div className="watch-row" key={project.id}><div>
            <Link href={`/app/projects/${project.id}`}>{project.name}<ArrowUpRight size={15} /></Link>
            <small>Последняя проверка: {formatDate(project.latest_scan?.created_at)}</small></div>
            <button className={`toggle ${project.watch ? "on" : ""}`} role="switch" aria-checked={project.watch} aria-label={`Мониторинг ${project.name}`} disabled={busy !== null} onClick={() => toggle(project)}><i /></button>
          </div>
        )) : <Empty title="Нет проектов" detail="Добавьте проект, чтобы включить мониторинг."><button className="button primary" onClick={create}><Plus size={17} />Добавить проект</button></Empty>}
      </div>
      <div className="report-section notification-section"><div className="report-title"><h2>Уведомления<span className="count">{notifications.length}</span></h2></div>
        {loading ? <Loading /> : notifications.length ? <div className="notifications">{notifications.map((notification) => <NotificationItem key={notification.id} notification={notification} />)}</div>
          : <Empty title="Уведомлений пока нет" detail="Новые события и результаты доставки появятся здесь." />}
      </div>
    </section>
  );
}

function GlobalHistory({ projects, create }: { projects: Project[]; create: () => void }) {
  const [scans, setScans] = useState<Array<Scan & { project: Project }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError("");
    Promise.allSettled(projects.map(async (project) => (await api<Scan[]>(`/projects/${project.id}/scans`)).map((scan) => ({ ...scan, project }))))
      .then((groups) => {
        if (!alive) return;
        setScans(groups.flatMap(group => group.status === "fulfilled" ? group.value : []).sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime()));
        if (groups.some(group => group.status === "rejected")) setError("Не удалось загрузить историю части проектов. Обновите страницу, чтобы повторить.");
      })
      .catch((failure) => { if (alive) setError(failure.message); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [projects]);
  return (
    <section>
      <div className="page-heading"><div><h1>История проверок</h1><p>Сохранённые результаты всех проектов.</p></div></div>
      {error && <ErrorBanner message={error} />}
      {loading ? <Loading /> : scans.length ? (
        <div className="report-section table-scroll"><table>
          <thead><tr><th>Проект</th><th>Проверка</th><th>Дата</th><th>Статус</th><th>Уязвимости</th></tr></thead>
          <tbody>{scans.map((scan) => <tr key={scan.id}>
            <td><Link className="table-title" href={`/app/projects/${scan.project.id}?tab=history`}>{scan.project.name}</Link></td>
            <td className="mono" title={scan.id}>{scan.report ? <Link className="text-button" href={`/app/projects/${scan.project.id}?tab=report&scan=${scan.id}`}>#{scan.id.slice(0, 8)}</Link> : <>#{scan.id.slice(0, 8)}</>}</td><td>{formatDate(scan.created_at)}</td>
            <td><span className={`status-badge ${scan.status}`}>{statusLabel(scan.status)}</span></td><td className="mono">{scan.report?.stats.findings ?? "н/д"}</td>
          </tr>)}</tbody>
        </table></div>
      ) : error ? <Empty title="История недоступна" detail="Не удалось получить сохранённые проверки."><button className="button secondary" onClick={() => window.location.reload()}>Повторить загрузку</button></Empty>
        : <Empty title="Нет сохранённых проверок" detail="Загрузите файл зависимостей, чтобы получить первый отчёт."><button className="button primary" onClick={create}><Plus size={17} />Добавить проект</button></Empty>}
    </section>
  );
}

function NotificationItem({ notification }: { notification: Notification }) {
  const categories: Record<string, string> = { new: "Новая уязвимость", priority: "Изменился приоритет", fix: "Доступно исправление", exploitation: "Подтверждённая эксплуатация", status: "Изменился статус" };
  const delivery: Record<string, string> = { pending: "В очереди", retry: "Повторная доставка", sending: "Отправляется", delivered: "Доставлено", failed: "Ошибка доставки", cancelled: "Отменено", awaiting_link: "Нужна привязка Telegram" };
  const finding = notification.payload.finding;
  return (
    <article><Bell size={18} /><div><strong>{categories[notification.category] || notification.category}</strong>
      <p><Link href={`/app/projects/${notification.project_id}`}>{notification.payload.project_name}</Link>{" · "}<span className="mono">{finding.package} {finding.version}</span><br />
        <span className="mono">{finding.id}</span>{" · "}приоритет {finding.priority}/100</p>
      <small>{formatDate(notification.created_at)}{" · "}{delivery[notification.status] || notification.status}{notification.attempts > 1 ? ` · попыток: ${notification.attempts}` : ""}</small>
    </div></article>
  );
}

