"use client";

import { useEffect, useState } from "react";
import { FlaskConical, ArrowRight, LoaderCircle, RefreshCw, Info } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { FixResult, Job, Scan } from "@/lib/types";
import { ErrorBanner, valueText, statusLabel, displayText } from "./ui";

const minimal = { title: "Точечное обновление", detail: "Обновления в пределах текущей minor-версии" };
const balanced = { title: "В пределах major-версии", detail: "Последние стабильные версии текущей major-ветки" };
const maximum = { title: "Полное обновление", detail: "Последние стабильные версии, включая новые major-ветки" };
const strategies: Record<string, { title: string; detail: string }> = {
  "Minimal Change": minimal,
  "Balanced": balanced,
  "Maximum Coverage": maximum,
  minimal,
  balanced,
  maximum,
};
const finishedStatuses = ["succeeded", "completed", "partial"];
const activeStatuses = ["queued", "pending", "retry", "running"];

function rememberJob(scanId: string, jobId: string | null) {
  try {
    if (jobId) sessionStorage.setItem(`paxveil-fixlab:${scanId}`, jobId);
    else sessionStorage.removeItem(`paxveil-fixlab:${scanId}`);
  } catch { /* The calculation still works when browser storage is unavailable. */ }
}

function GraphChanges({ value }: { value: unknown }) {
  if (!value || typeof value !== "object") return <p className="muted">Нет данных</p>;
  const changes = value as Record<string, unknown>;
  const sections = [
    { key: "changed", title: "Обновлены" },
    { key: "added", title: "Добавлены" },
    { key: "removed", title: "Удалены" },
  ];

  if (!sections.some(section => Array.isArray(changes[section.key]))) {
    return <pre className="data-block">{valueText(value)}</pre>;
  }
  const total = sections.reduce((count, section) => count + (Array.isArray(changes[section.key]) ? (changes[section.key] as unknown[]).length : 0), 0);
  if (total === 0) return <p className="muted">Состав пакетов не изменился.</p>;

  return <>{sections.map(section => {
    const rows = changes[section.key];
    if (!Array.isArray(rows) || !rows.length) return null;
    return (
      <div key={section.key}>
        <h4>{section.title}</h4>
        <ul className="update-list">
          {rows.map((row, index) => {
            if (!row || typeof row !== "object") return <li key={index}>{valueText(row)}</li>;
            const item = row as Record<string, unknown>;
            return (
              <li key={index}>
                <strong className="mono">{valueText(item.package)}</strong>
                <span className="mono">
                  {section.key === "changed"
                    ? <>{valueText(item.from)} <ArrowRight size={12} /> {valueText(item.to)}</>
                    : valueText(item.version)}
                </span>
              </li>
            );
          })}
        </ul>
      </div>
    );
  })}</>;
}

export function FixLab({ scan }: { scan: Scan }) {
  const [job, setJob] = useState<Job | null>(null);
  const [result, setResult] = useState<FixResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setResult(null);
    setJob(null);
    setError("");
    setBusy(false);
    let alive = true;
    let previous: string | null = null;
    try { previous = sessionStorage.getItem(`paxveil-fixlab:${scan.id}`); } catch { return; }
    if (!previous) return;
    setBusy(true);
    api<Job>(`/jobs/${previous}`).then(data => {
      if (!alive) return;
      setJob(data);
      if (finishedStatuses.includes(data.status)) setResult(data.result as FixResult);
      if (data.status === "failed") setError(data.error || "Расчёт завершился с ошибкой");
      setBusy(activeStatuses.includes(data.status));
    }).catch(error => {
      if (!alive) return;
      if (error instanceof ApiError && [401, 404].includes(error.status)) {
        rememberJob(scan.id, null);
        setBusy(false);
      } else {
        setJob({ id: previous!, status: "pending", kind: "fixlab", result: null, error: null, attempts: 0 });
        setError("Не удалось восстановить статус расчёта. Повторяем запрос автоматически.");
      }
    });
    return () => { alive = false; };
  }, [scan.id]);

  useEffect(() => {
    if (!job || !activeStatuses.includes(job.status)) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const data = await api<Job>(`/jobs/${job!.id}`);
        if (cancelled) return;
        setJob(data);
        setError("");
        if (finishedStatuses.includes(data.status)) {
          setResult(data.result as FixResult);
          setBusy(false);
        }
        if (data.status === "failed") {
          setError(data.error || "Расчёт завершился с ошибкой");
          setBusy(false);
        }
        if (activeStatuses.includes(data.status)) timer = setTimeout(poll, 2500);
      } catch (error) {
        if (!cancelled) {
          if (error instanceof ApiError && [401, 404].includes(error.status)) {
            rememberJob(scan.id, null);
            setJob(null);
            setBusy(false);
            setError("Сохранённый расчёт больше недоступен. Обновите страницу или запустите новый.");
            return;
          }
          setError("Связь прервалась. Расчёт продолжится на сервере, а страница повторит запрос автоматически.");
          timer = setTimeout(poll, 5000);
        }
      }
    }
    timer = setTimeout(poll, 2000);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [job?.id, job?.status]);

  async function run() {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const data = await api<{ id: string; status: string }>(`/scans/${scan.id}/fixlab`, { method: "POST" });
      rememberJob(scan.id, data.id);
      setJob({ ...data, kind: "fixlab", result: null, error: null, attempts: 0 });
    } catch (error) {
      setError(error instanceof Error ? error.message : "Не удалось запустить расчёт");
      setBusy(false);
    }
  }

  return (
    <section>
      <div className="tool-intro">
        <div>
          <h2>Варианты обновления</h2>
          <p>FixLab подбирает версии, проверяет совместимость зависимостей по метаданным и повторяет поиск уязвимостей.</p>
        </div>
        <button className="button primary" disabled={busy} onClick={run}>
          {busy ? <LoaderCircle size={17} className="spin" /> : result ? <RefreshCw size={17} /> : <FlaskConical size={17} />}
          {busy ? "Расчёт идёт" : result ? "Пересчитать" : "Рассчитать варианты"}
        </button>
      </div>
      {error && <ErrorBanner message={error} retry={busy ? undefined : run} />}
      <p className="analysis-note">
        <Info size={16} /> Код и тесты приложения не запускаются. Совместимость обновлений нужно проверить перед применением.
      </p>
      {busy && (
        <div role="status" className="job-progress">
          <LoaderCircle size={20} className="spin" />
          <div>
            <strong>{job ? statusLabel(job.status) : "Подготовка расчёта"}</strong>
            <p>PyPI, разрешение зависимостей и повторная проверка OSV. Это может занять несколько минут. Можно перейти в другой раздел и вернуться к расчёту.</p>
          </div>
        </div>
      )}
      {!result && !busy && (
        <div className="strategy-placeholder">
          {[minimal, balanced, maximum].map((strategy, index) => (
            <div key={strategy.title}>
              <span className="strategy-label">{String.fromCharCode(65 + index)}</span>
              <h3>{strategy.title}</h3>
              <p>{strategy.detail}</p>
            </div>
          ))}
        </div>
      )}
      {result && (
        <>
          <div className="strategies">
            {result.strategies.map((strategy, index) => (
              <article className="strategy" key={strategy.name}>
                <header>
                  <span className="strategy-label">{String.fromCharCode(65 + index)}</span>
                  <h3>{strategies[strategy.name]?.title || strategy.name}</h3>
                  <span className={`status-badge ${strategy.status === "resolved" ? "completed" : "partial"}`}>
                    {({ resolved: "Расчёт завершён", conflict: "Конфликт зависимостей", insufficient_data: "Недостаточно данных" }[strategy.status] || strategy.status)}
                  </span>
                </header>
                <div className="fix-count">
                  <div><span>Сейчас</span><strong>{strategy.before.findings}</strong></div>
                  <ArrowRight size={21} />
                  <div><span>После обновления</span>
                    <strong className={strategy.status === "resolved" && strategy.after?.findings === 0
                      ? "text-success" : strategy.after?.findings ? "text-danger" : "muted"}>
                      {strategy.after ? strategy.after.findings : "н/д"}
                    </strong>
                  </div>
                </div>
                <p className="form-hint">Известные уязвимости</p>
                <h4>Изменения версий</h4>
                {strategy.updates.length ? (
                  <ul className="update-list">
                    {strategy.updates.map((update, updateIndex) => (
                      <li key={updateIndex}>
                        <strong className="mono">{update.package}</strong>
                        <span className="mono">{update.from} <ArrowRight size={12} /> {update.to}</span>
                      </li>
                    ))}
                  </ul>
                ) : <p className="muted">Подходящие обновления не найдены.</p>}
                <p className="strategy-reason">{displayText(strategy.reason)}</p>
                {strategy.conflicts.length > 0 && (
                  <div className="conflict-list">
                    <h4>Конфликты</h4>
                    {strategy.conflicts.map((conflict, conflictIndex) => <pre key={conflictIndex}>{valueText(conflict)}</pre>)}
                  </div>
                )}
                {strategy.uncertainties.length > 0 && (
                  <details>
                    <summary>Ограничения расчёта ({strategy.uncertainties.length})</summary>
                    <ul>{strategy.uncertainties.map((uncertainty, uncertaintyIndex) => <li key={uncertaintyIndex}>{valueText(uncertainty)}</li>)}</ul>
                  </details>
                )}
                <details><summary>Изменения состава пакетов</summary><GraphChanges value={strategy.graph_changes} /></details>
              </article>
            ))}
          </div>
          {result.limitations.length > 0 && (
            <details className="limitations report-limitations">
              <summary><Info size={17} /> Условия расчёта</summary>
              <ul>{result.limitations.map((limitation, index) => <li key={index}>{displayText(limitation)}</li>)}</ul>
            </details>
          )}
        </>
      )}
    </section>
  );
}
