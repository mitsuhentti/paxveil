"use client";

import { useState } from "react";
import Link from "next/link";
import { Search, LoaderCircle, ArrowUpRight, AlertTriangle, Info } from "lucide-react";
import { api, json } from "@/lib/api";
import type { FireResult } from "@/lib/types";
import { ErrorBanner, External, statusLabel, displayText } from "./ui";

export function FireDrill() {
  const [cve, setCve] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<FireResult | null>(null);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setResult(null);
    try {
      setResult(await api<FireResult>("/fire", {
        method: "POST",
        body: json({ cve: cve.trim().toUpperCase() }),
      }));
    } catch (error) {
      setError(error instanceof Error ? error.message : "Не удалось проверить CVE");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <div className="page-heading">
        <div>
          <h1>Проверка CVE</h1>
          <p>Найдите конкретную уязвимость в сохранённых проектах.</p>
        </div>
      </div>
      <form className="fire-form" onSubmit={submit}>
        <label htmlFor="cve">Номер CVE</label>
        <div>
          <span className="search-box">
            <Search size={18} />
            <input
              id="cve"
              value={cve}
              onChange={event => setCve(event.target.value)}
              required
              pattern="[Cc][Vv][Ee]-[0-9]{4}-[0-9]{4,}"
              placeholder="CVE-2024-35195"
              className="mono"
              autoComplete="off"
            />
          </span>
          <button disabled={busy} className="button primary">
            {busy ? <LoaderCircle size={17} className="spin" /> : <Search size={17} />}
            {busy ? "Проверка идёт" : "Проверить проекты"}
          </button>
        </div>
        <p className="form-hint">Проверка использует последние сохранённые версии пакетов и данные OSV.</p>
      </form>
      {error && <ErrorBanner message={error} />}
      {busy && <div className="loading-state" role="status"><LoaderCircle size={22} className="spin" /><span>Поиск CVE в OSV и проектах</span></div>}
      {!result && !busy && (
        <div className="fire-explanation">
          <div><span className="status-dot ok" /><strong>Совпадение</strong><p>Сохранённая версия входит в уязвимый диапазон.</p></div>
          <div><span className="status-dot warning" /><strong>Возможное совпадение</strong><p>Пакет найден, но версия требует уточнения.</p></div>
          <div><span className="status-dot" /><strong>Недостаточно данных</strong><p>Источник или версия недоступны для проверки.</p></div>
        </div>
      )}
      {result && (
        <div className="fire-result">
          <div className="report-title">
            <h2 className="mono">{result.cve}</h2>
            <span className={`status-badge ${result.status === "confirmed" ? "failed" : result.status === "no_match" ? "no_match" : "partial"}`}>
              {statusLabel(result.status)}
            </span>
          </div>
          {result.status === "insufficient_data" && (
            <p className="coverage-notice"><AlertTriangle size={16} /> Данных недостаточно, чтобы исключить риск для проектов.</p>
          )}
          {result.matches.length ? result.matches.map((match, index) => (
            <article key={index} className="fire-match">
              <div className="fire-match-heading">
                <div>
                  <Link href={`/app/projects/${match.project_id}`}>{match.project_name}<ArrowUpRight size={15} /></Link>
                  <h3 className="mono">{match.package} <span className="muted">{match.version || "Версия не указана"}</span></h3>
                </div>
                <span className="meta-pill">{statusLabel(match.status)}</span>
              </div>
              <p>Запись OSV: <strong className="mono">{match.advisory_id}</strong></p>
              {match.path?.length > 1 && <p className="dependency-path mono">{match.path.join(" → ")}</p>}
              <p>Версии с исправлением: <span className="mono">{match.fixed_versions.join(", ") || "Не указаны"}</span></p>
              <div className="reference-list">
                {match.references.map((reference, referenceIndex) => (
                  <External key={referenceIndex} url={typeof reference === "string" ? reference : reference.url} />
                ))}
              </div>
            </article>
          )) : (
            <div className="inline-empty">
              <strong>Совпадений в сохранённых данных нет</strong>
              <p>Обновите отчёты, если зависимости изменились. Этот результат не подтверждает отсутствие риска.</p>
            </div>
          )}
          <p className="analysis-note">
            <Info size={16} /> При совпадении проверьте условия эксплуатации и варианты обновления в проекте.
          </p>
          {result.limitations.length > 0 && (
            <details className="limitations report-limitations">
              <summary><AlertTriangle size={17} /> Ограничения проверки</summary>
              <ul>{result.limitations.map((limitation, index) => <li key={index}>{displayText(limitation)}</li>)}</ul>
            </details>
          )}
        </div>
      )}
    </section>
  );
}
