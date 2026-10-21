"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  RefreshCw, LoaderCircle, Radar, Trash2, ChevronLeft,
  FileText, GitBranch, FlaskConical, Clock3,
} from "lucide-react";
import { api, formatDate, json } from "@/lib/api";
import type { Project, Scan } from "@/lib/types";
import { Empty, ErrorBanner, Loading, Modal, statusLabel } from "./ui";
import { ReportView } from "./report";
import { DependencyGraph } from "./graph";
import { FixLab } from "./fixlab";

const tabs = [
  { id: "report", label: "Отчёт", icon: FileText },
  { id: "graph", label: "Зависимости", icon: GitBranch },
  { id: "fixlab", label: "Обновления", icon: FlaskConical },
  { id: "history", label: "История", icon: Clock3 },
];

export function ProjectView({
  id, changed, deleted, notify,
}: {
  id: string;
  changed: () => void;
  deleted: () => void;
  notify: (message: string) => void;
}) {
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("report");
  const [busy, setBusy] = useState(false);
  const [remove, setRemove] = useState(false);
  const [scans, setScans] = useState<Scan[]>([]);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [historical, setHistorical] = useState<Scan | null>(null);
  const [openingScan, setOpeningScan] = useState(false);

  useEffect(() => {
    const search = new URLSearchParams(window.location.search);
    const requested = search.get("tab");
    const requestedScan = search.get("scan");
    setTab(tabs.some(item => item.id === requested) ? requested! : "report");
    setHistorical(null);
    setProject(null);
    setError("");
    let alive = true;

    api<Project>(`/projects/${id}`)
      .then(async data => {
        if (!alive) return;
        setProject(data);
        if (!requestedScan) return;
        setOpeningScan(true);
        try {
          const history = await api<Scan[]>(`/projects/${id}/scans`);
          if (!alive) return;
          const report = history.find(item => item.id === requestedScan);
          if (report?.report) setHistorical(report);
          else setError("Сохранённый отчёт не найден. Открыта последняя проверка проекта.");
        } finally { if (alive) setOpeningScan(false); }
      })
      .catch(error => { if (alive) setError(error.message); });

    return () => { alive = false; };
  }, [id]);

  useEffect(() => {
    if (!project?.latest_scan || !["queued", "running"].includes(project.latest_scan.status)) return;
    let alive = true;
    const timer = setInterval(() => {
      api<Project>(`/projects/${id}`)
        .then(data => {
          if (!alive) return;
          setProject(data);
          if (!["queued", "running"].includes(data.latest_scan?.status || "")) changed();
        })
        .catch(error => { if (alive) setError(error.message); });
    }, 2500);

    return () => { alive = false; clearInterval(timer); };
  }, [id, project?.latest_scan?.status, changed]);

  useEffect(() => {
    if (tab !== "history") return;
    let alive = true;
    setHistoryBusy(true);
    api<Scan[]>(`/projects/${id}/scans`)
      .then(data => { if (alive) setScans(data); })
      .catch(error => { if (alive) setError(error.message); })
      .finally(() => { if (alive) setHistoryBusy(false); });

    return () => { alive = false; };
  }, [tab, id, project?.latest_scan?.status]);

  async function rescan() {
    setBusy(true);
    setError("");
    try {
      await api(`/projects/${id}/scan`, { method: "POST" });
      setProject(await api<Project>(`/projects/${id}`));
      setHistorical(null);
      const url = new URL(window.location.href);
      url.searchParams.delete("scan");
      window.history.replaceState(null, "", url);
      selectTab("report");
      changed();
      notify("Проверка поставлена в очередь");
    } catch (error) {
      setError(error instanceof Error ? error.message : "Не удалось запустить проверку");
    } finally {
      setBusy(false);
    }
  }

  async function watch() {
    if (!project) return;
    setBusy(true);
    setError("");
    try {
      const data = await api<{ enabled: boolean }>(`/projects/${id}/watch`, {
        method: "PUT",
        body: json({ enabled: !project.watch }),
      });
      setProject({ ...project, watch: data.enabled });
      changed();
      notify(data.enabled ? "Мониторинг включён" : "Мониторинг выключен");
    } catch (error) {
      setError(error instanceof Error ? error.message : "Не удалось изменить мониторинг");
    } finally {
      setBusy(false);
    }
  }

  async function deleteProject() {
    setBusy(true);
    setError("");
    try {
      await api(`/projects/${id}`, { method: "DELETE" });
      setRemove(false);
      deleted();
      notify("Проект удалён");
    } catch (error) {
      setError(error instanceof Error ? error.message : "Не удалось удалить проект");
    } finally {
      setBusy(false);
    }
  }

  function openScan(scan: Scan) {
    setHistorical(scan);
    setError("");
    const url = new URL(window.location.href);
    url.searchParams.set("scan", scan.id);
    window.history.replaceState(null, "", url);
    selectTab("report");
  }

  function latestReport() {
    setHistorical(null);
    const url = new URL(window.location.href);
    url.searchParams.delete("scan");
    window.history.replaceState(null, "", url);
  }

  function selectTab(value: string) {
    setTab(value);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", value);
    window.history.replaceState(null, "", url);
  }

  function moveTab(event: React.KeyboardEvent, index: number) {
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else return;
    event.preventDefault();
    selectTab(tabs[next].id);
    document.getElementById(`tab-${tabs[next].id}`)?.focus();
  }

  if (!project) {
    return error
      ? <ErrorBanner message={error} retry={() => window.location.reload()} />
      : <Loading text="Загрузка проекта" />;
  }

  const scan = historical || project.latest_scan;
  const running = ["queued", "running"].includes(project.latest_scan?.status || "");
  const environment = project.latest_scan?.report?.environment;

  return (
    <section>
      <Link href="/app" className="back-link"><ChevronLeft size={16} /> Все проекты</Link>
      <div className="page-heading project-heading">
        <div>
          <div className="project-context">
            <span>Python{environment && ` ${environment.python_version}`}</span>
            {environment && <span>{environment.platform}</span>}
          </div>
          <h1>{project.name}</h1>
          <p>
            {project.latest_scan ? <>{running ? "Запущено" : "Проверка от"} {formatDate(project.latest_scan.created_at)}</> : "Проверок пока нет"}
            {project.latest_scan && (
              <span className={`status-badge ${project.latest_scan.status}`}>
                {statusLabel(project.latest_scan.status)}
              </span>
            )}
          </p>
        </div>
        <div className="heading-actions">
          <button
            className={`button secondary ${project.watch ? "watch-active" : ""}`}
            disabled={busy}
            onClick={watch}
            aria-pressed={project.watch}
          >
            <Radar size={16} /> {project.watch ? "Мониторинг включён" : "Мониторинг"}
          </button>
          <button className="button primary" disabled={busy || running} onClick={rescan}>
            {running ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />}
            {running ? "Проверка идёт" : "Проверить снова"}
          </button>
          <button className="icon-button danger" aria-label="Удалить проект" disabled={busy} onClick={() => setRemove(true)}>
            <Trash2 size={17} />
          </button>
        </div>
      </div>
      {error && <ErrorBanner message={error} />}
      <div className="project-tabs" role="tablist" aria-label="Разделы проекта">
        {tabs.map((item, index) => (
          <button
            key={item.id}
            id={`tab-${item.id}`}
            role="tab"
            aria-selected={tab === item.id}
            aria-controls="project-panel"
            tabIndex={tab === item.id ? 0 : -1}
            className={tab === item.id ? "active" : ""}
            onClick={() => selectTab(item.id)}
            onKeyDown={event => moveTab(event, index)}
          >
            <item.icon size={16} /> {item.label}
          </button>
        ))}
      </div>
      <div id="project-panel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
        {openingScan ? <Loading text="Открывается сохранённый отчёт" /> : tab === "history" ? (
          historyBusy ? <Loading /> : scans.length ? (
            <section className="history-section report-section">
              <div className="report-title"><h2>Предыдущие проверки</h2><span className="count">{scans.length}</span></div>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr><th>Проверка</th><th>Дата</th><th>Статус</th><th>Пакеты</th><th>Уязвимости</th><th>Отчёт</th></tr>
                  </thead>
                  <tbody>
                    {scans.map(item => (
                      <tr key={item.id}>
                        <td>{item.id === project.latest_scan?.id ? "Последняя" : "Сохранённая"}</td>
                        <td>{formatDate(item.created_at)}</td>
                        <td><span className={`status-badge ${item.status}`}>{statusLabel(item.status)}</span></td>
                        <td>{item.report?.stats.dependencies ?? "н/д"}</td>
                        <td>{item.report?.stats.findings ?? "н/д"}</td>
                        <td>
                          <button
                            className="text-button"
                            disabled={!["completed", "partial"].includes(item.status)}
                            onClick={() => openScan(item)}
                          >Открыть</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : <Empty title="История пуста" detail="Здесь появятся отчёты после первой проверки." />
        ) : !scan ? (
          <Empty title="Проект ещё не проверен" detail="Запустите проверку, чтобы получить отчёт по зависимостям."><button className="button primary" disabled={busy} onClick={rescan}><RefreshCw size={17} />Проверить проект</button></Empty>
        ) : ["queued", "running"].includes(scan.status) ? (
          <div className="scan-progress" role="status">
            <span className="scan-loader"><Radar size={32} /></span>
            <h2>{scan.status === "queued" ? "Проверка в очереди" : "Проверка зависимостей"}</h2>
            <p>Загрузка данных OSV и метаданных пакетов. Отчёт появится автоматически.</p>
          </div>
        ) : scan.status === "failed" ? (
          <ErrorBanner message={scan.error || "Проверка завершилась с ошибкой."} retry={rescan} />
        ) : scan.report ? (
          <>
            {historical && (
              <div className="historical-banner">
                <span>Отчёт от {formatDate(historical.created_at)}</span>
                <button onClick={latestReport}>Последний отчёт</button>
              </div>
            )}
            {tab === "graph" ? <DependencyGraph report={scan.report} /> : tab === "fixlab" ? <FixLab key={scan.id} scan={scan} /> : (
              <ReportView
                key={scan.id}
                report={scan.report}
                updates={() => selectTab("fixlab")}
                projectId={historical ? undefined : project.id}
                changed={() => {
                  api<Project>(`/projects/${id}`).then(setProject).catch(error => setError(error.message));
                  changed();
                }}
              />
            )}
          </>
        ) : <Empty title="Отчёт недоступен" detail="Запустите проверку снова, чтобы получить свежий отчёт."><button className="button primary" disabled={busy || running} onClick={rescan}><RefreshCw size={17} />Проверить снова</button></Empty>}
      </div>
      <Modal
        open={remove}
        onOpenChange={value => { if (!busy) setRemove(value); }}
        title="Удалить проект?"
        description={`Проект «${project.name}», все отчёты и настройки мониторинга будут удалены.`}
      >
        <div className="modal-actions">
          <button className="button secondary" disabled={busy} onClick={() => setRemove(false)}>Отмена</button>
          <button className="button destructive" disabled={busy} onClick={deleteProject}>
            {busy && <LoaderCircle className="spin" size={16} />} Удалить проект
          </button>
        </div>
      </Modal>
    </section>
  );
}
