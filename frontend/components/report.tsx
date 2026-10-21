"use client";

import { useMemo, useState } from "react";
import { Search, ArrowUpDown, ChevronRight, AlertTriangle, Info, LoaderCircle, ArrowRight } from "lucide-react";
import type { Finding, Report, Severity } from "@/lib/types";
import { api, formatDate, json } from "@/lib/api";
import { Empty, Modal, External, valueText, ErrorBanner, displayText, statusLabel } from "./ui";

const severityLabels: Record<Severity, string> = {
  critical: "Критическая",
  high: "Высокая",
  medium: "Средняя",
  low: "Низкая",
  unknown: "Нет оценки",
};
const completenessLabels: Record<string, string> = {
  complete: "Проверка завершена",
  recorded_versions_checked: "Проверены указанные версии",
  partial: "Неполные данные",
  incomplete: "Неполные данные",
  insufficient_data: "Недостаточно данных",
};
const dependencyStatusLabels: Record<string, string> = {
  active: "Входит в окружение",
  excluded: "Не входит в окружение",
  uncertain: "Требует уточнения",
  unresolved: "Версия неизвестна",
  unsupported: "Не поддерживается",
  version_not_found: "Версия не найдена",
};
const sourceLabels: Record<string, string> = {
  ok: "Получены",
  success: "Получены",
  cached: "Из кеша",
  partial: "Частично",
  failed: "Недоступны",
  error: "Ошибка",
  unavailable: "Недоступны",
};
const epssText = (value: number | null) => value === null ? "н/д" : `${(value * 100).toFixed(2)}%`;

export function ReportView({
  report, projectId, changed, updates,
}: {
  report: Report;
  projectId?: string;
  changed?: () => void;
  updates?: () => void;
}) {
  const [query, setQuery] = useState("");
  const [severity, setSeverity] = useState("all");
  const [sort, setSort] = useState("priority");
  const [processingStatus, setProcessingStatus] = useState("all");
  const [selected, setSelected] = useState<Finding | null>(null);
  const [dependencyQuery, setDependencyQuery] = useState("");
  const [statusBusy, setStatusBusy] = useState(false);
  const [statusError, setStatusError] = useState("");

  const findings = useMemo(() => {
    const filtered = report.findings.filter(finding => {
      const matchesSeverity = severity === "all" || finding.severity === severity;
      const searchText = `${finding.id} ${finding.aliases.join(" ")} ${finding.package} ${finding.summary}`;
      return matchesSeverity && (processingStatus === "all" || finding.status === processingStatus)
        && searchText.toLowerCase().includes(query.trim().toLowerCase());
    });
    return filtered.sort((a, b) => {
      if (sort === "package") return a.package.localeCompare(b.package);
      if (sort === "epss") return (b.epss ?? -1) - (a.epss ?? -1);
      return b.priority - a.priority;
    });
  }, [report.findings, severity, processingStatus, query, sort]);
  const dependencies = report.dependencies.filter(dependency =>
    `${dependency.name} ${dependency.version}`.toLowerCase().includes(dependencyQuery.trim().toLowerCase()),
  );
  const partial = !["complete", "recorded_versions_checked"].includes(report.completeness);
  const filtered = Boolean(query.trim()) || severity !== "all" || processingStatus !== "all";

  function resetFilters() { setQuery(""); setSeverity("all"); setProcessingStatus("all"); }

  function openFinding(finding: Finding) {
    setSelected(finding);
    setStatusError("");
  }

  async function changeStatus(status: string) {
    if (!selected || !projectId) return;
    setStatusBusy(true);
    setStatusError("");
    try {
      const result = await api<{ status: string }>(`/projects/${projectId}/finding-status`, {
        method: "PUT",
        body: json({ advisory_id: selected.id, package: selected.package, status }),
      });
      setSelected(current => current?.id === selected.id && current.package === selected.package
        ? { ...current, status: result.status }
        : current);
      changed?.();
    } catch (error) {
      setStatusError(error instanceof Error ? error.message : "Не удалось сохранить статус");
    } finally {
      setStatusBusy(false);
    }
  }

  return (
    <div>
      <div className="report-metrics">
        <div><span>Пакеты</span><strong>{report.stats.dependencies}</strong><small>В загруженном файле</small></div>
        <div>
          <span>Уязвимости</span>
          <strong className={report.findings.length ? "text-danger" : ""}>{report.stats.findings}</strong>
          <small>Совпадения по версии</small>
        </div>
        <div>
          <span>Высокий приоритет</span>
          <strong>{report.findings.filter(finding => finding.priority >= 70).length}</strong>
          <small>От 70 баллов из 100</small>
        </div>
        <div>
          <span>Время проверки</span>
          <strong>{report.stats.duration_seconds.toFixed(1)}<em>с</em></strong>
          <small>Python {report.environment.python_version} · {report.environment.platform}</small>
        </div>
      </div>

      {report.findings.length > 0 && updates && <div className="next-action">
        <div><strong>Следующий шаг: подобрать обновления</strong><p>Сравните версии, совместимость зависимостей и результат повторной проверки.</p></div>
        <button className="button secondary" onClick={updates}>Варианты обновления<ArrowRight size={16} /></button>
      </div>}

      <section className="report-section">
        <div className="report-title">
          <h2>Уязвимости <span className="count">{report.findings.length}</span></h2>
          <span className="meta-pill">{completenessLabels[report.completeness] || "Проверьте ограничения"}</span>
        </div>
        {partial && (
          <p className="coverage-notice">
            <AlertTriangle size={16} /> Часть данных недоступна. Подробности в ограничениях проверки.
          </p>
        )}
        <div className="table-toolbar">
          <label className="search-box">
            <Search size={17} />
            <input
              aria-label="Поиск уязвимостей"
              placeholder="Пакет или CVE"
              value={query}
              onChange={event => setQuery(event.target.value)}
            />
          </label>
          <label className="sr-only" htmlFor="severity">Уровень риска</label>
          <select id="severity" value={severity} onChange={event => setSeverity(event.target.value)}>
            <option value="all">Все уровни риска</option>
            {Object.entries(severityLabels).map(([key, label]) => <option value={key} key={key}>{label}</option>)}
          </select>
          <select aria-label="Статус уязвимости" value={processingStatus} onChange={event => setProcessingStatus(event.target.value)}>
            <option value="all">Все статусы</option>
            <option value="open">Открыта</option><option value="investigating">На проверке</option>
            <option value="accepted">Риск принят</option><option value="resolved">Закрыта</option>
          </select>
          <div className="sort-control">
            <ArrowUpDown size={15} />
            <select aria-label="Сортировка уязвимостей" value={sort} onChange={event => setSort(event.target.value)}>
              <option value="priority">По приоритету</option>
              <option value="epss">По EPSS</option>
              <option value="package">По пакету</option>
            </select>
          </div>
        </div>
        {filtered && <div className="filter-summary"><span role="status">Показано {findings.length} из {report.findings.length}</span><button className="text-button" onClick={resetFilters}>Сбросить фильтры</button></div>}
        {findings.length ? (
          <div className="table-scroll">
            <table className="findings-table">
              <thead>
                <tr>
                  <th>Пакет и уязвимость</th><th>Уровень риска</th><th>Приоритет</th>
                  <th>CVSS</th><th>EPSS</th><th>Исправлено в</th><th><span className="sr-only">Подробнее</span></th>
                </tr>
              </thead>
              <tbody>
                {findings.map(finding => (
                  <tr key={`${finding.package}-${finding.version}-${finding.id}`}>
                    <td>
                      <button className="table-title" onClick={() => openFinding(finding)}>
                        {finding.package}<span className="mono">{finding.version}</span>
                      </button>
                      <span className="advisory-id mono">{finding.id}</span>
                      <span className="finding-table-status">{statusLabel(finding.status)}</span>
                    </td>
                    <td>
                      <span className={`severity ${finding.severity}`}>{severityLabels[finding.severity]}</span>
                      {finding.kev === true && <small className="kev">CISA KEV</small>}
                    </td>
                    <td>
                      <div className="priority-cell">
                        <span>{finding.priority}</span>
                        <i aria-hidden="true"><b style={{ width: `${finding.priority}%` }} /></i>
                      </div>
                    </td>
                    <td className="mono">{finding.cvss ?? "н/д"}</td>
                    <td className="mono">{epssText(finding.epss)}</td>
                    <td className="mono">{finding.fixed_versions.slice(0, 2).join(", ") || "н/д"}</td>
                    <td>
                      <button className="icon-button" aria-label={`Подробнее ${finding.id} ${finding.package}`} onClick={() => openFinding(finding)}>
                        <ChevronRight size={18} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title={report.findings.length ? "Нет совпадений с фильтром" : partial ? "Проверка не завершена полностью" : "Известные уязвимости не найдены"}
            detail={report.findings.length
              ? "Измените условия поиска или сбросьте фильтры."
              : partial ? "Пустой список не подтверждает отсутствие уязвимостей. Проверьте недоступные источники и ограничения ниже."
                : "Результат относится к указанным версиям и доступным источникам. Проверьте ограничения ниже."}
          >{filtered && <button className="button secondary" onClick={resetFilters}>Сбросить фильтры</button>}</Empty>
        )}
      </section>

      <p className="analysis-note">
        <Info size={16} /> CVSS оценивает серьёзность, EPSS оценивает вероятность эксплуатации CVE. Использование уязвимого кода в приложении не проверялось.
      </p>
      {report.warnings.length > 0 && (
        <details className="limitations report-limitations">
          <summary><AlertTriangle size={17} /> Ограничения проверки <span className="count">{report.warnings.length}</span></summary>
          <ul>{report.warnings.map((warning, index) => <li key={index}>{displayText(warning)}</li>)}</ul>
        </details>
      )}
      <details className="dependency-list">
        <summary>Пакеты из файла <span className="count">{report.dependencies.length}</span></summary>
        <label className="search-box">
          <Search size={17} />
          <input
            aria-label="Поиск в зависимостях"
            placeholder="Название пакета"
            value={dependencyQuery}
            onChange={event => setDependencyQuery(event.target.value)}
          />
        </label>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Пакет</th><th>Версия</th><th>Тип зависимости</th><th>Статус</th></tr></thead>
            <tbody>
              {dependencies.map((dependency, index) => (
                <tr key={`${dependency.name}-${index}`}>
                  <td className="mono">{dependency.name}</td>
                  <td className="mono">{dependency.version || "Не указана"}</td>
                  <td>{dependency.direct === null ? "Не определён" : dependency.direct ? "Прямая" : "Транзитивная"}</td>
                  <td>
                    {dependencyStatusLabels[dependency.status] || dependency.status}
                    {dependency.marker && <small className="mono">{dependency.marker}</small>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!dependencies.length && <Empty title="Пакеты не найдены" detail="Попробуйте другое название."><button className="button secondary" onClick={() => setDependencyQuery("")}>Сбросить поиск</button></Empty>}
      </details>

      <section className="source-status report-section">
        <div className="report-title"><h2>Источники данных</h2></div>
        <div className="table-scroll">
          <table className="source-table">
            <thead><tr><th>Источник</th><th>Данные</th><th>Получены</th></tr></thead>
            <tbody>
              {report.sources.map((source, index) => (
                <tr key={`${source.name}-${index}`}>
                  <td><strong>{source.name}</strong></td>
                  <td>
                    <span className={`status-dot ${["ok", "success", "cached"].includes(source.status) ? "ok" : "warning"}`} />
                    {sourceLabels[source.status] || source.status}
                  </td>
                  <td>
                    <time>{formatDate(source.fetched_at)}</time>
                    {source.error && <small>{displayText(source.error)}</small>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <Modal
        open={!!selected}
        onOpenChange={open => { if (!open) setSelected(null); }}
        title={selected?.id || "Уязвимость"}
        description={selected ? `${selected.package} ${selected.version} · ${severityLabels[selected.severity]}` : ""}
        wide
      >
        {selected && (
          <div className="finding-detail">
            <div className="finding-heading"><h3>{selected.summary ? displayText(selected.summary) : "Описание отсутствует"}</h3></div>
            <div className="detail-grid">
              <div><span>Приоритет</span><strong>{selected.priority} / 100</strong></div>
              <div><span>CVSS</span><strong>{selected.cvss ?? "Нет данных"}</strong></div>
              <div><span>EPSS</span><strong>{selected.epss === null ? "Нет данных" : epssText(selected.epss)}</strong></div>
              <div>
                <span>Каталог CISA KEV</span>
                <strong>{selected.kev === true ? "Есть в каталоге" : selected.kev === false ? "Нет в каталоге" : "Нет данных"}</strong>
              </div>
            </div>
            <div className="finding-status-control finding-processing">
              <label>
                Статус обработки
                <select
                  aria-label="Статус обработки"
                  value={selected.status}
                  disabled={statusBusy || !projectId}
                  onChange={event => changeStatus(event.target.value)}
                >
                  <option value="open">Открыта</option><option value="investigating">На проверке</option>
                  <option value="accepted">Риск принят</option><option value="resolved">Закрыта</option>
                </select>
              </label>
              {statusBusy && <LoaderCircle size={16} className="spin" />}
              {!projectId && <p className="form-hint">Сохранённый отчёт. Статус можно изменить в последней проверке.</p>}
            </div>
            {statusError && <ErrorBanner message={statusError} />}
            <h4>Расчёт приоритета</h4>
            <ul>{selected.priority_reasons.map((reason, index) => <li key={index}>{displayText(reason)}</li>)}</ul>
            <h4>Версии с исправлением</h4>
            <p className="mono">{selected.fixed_versions.join(", ") || "Не указаны источником"}</p>
            <details>
              <summary>Затронутые версии</summary>
              <pre className="data-block">{valueText(selected.affected)}</pre>
            </details>
            <div className="detail-meta">
              <span>Опубликовано: {formatDate(selected.published)}</span>
              <span>Обновлено: {formatDate(selected.modified)}</span>
              <span>Дата EPSS: {selected.epss_date || "Нет данных"}</span>
              <span>Статус: {statusLabel(selected.status)}</span>
            </div>
            {selected.aliases.length > 0 && <p className="mono muted">{selected.aliases.join(" · ")}</p>}
            <h4>Ссылки</h4>
            <div className="reference-list">
              {selected.references.map((reference, index) => (
                <External key={index} url={typeof reference === "string" ? reference : reference.url} />
              ))}
            </div>
            <p className="form-hint">Варианты обновления доступны на вкладке «Обновления». Перед применением проверьте совместимость.</p>
            {updates && <button className="button secondary" onClick={() => { setSelected(null); updates(); }}>Подобрать обновления<ArrowRight size={16} /></button>}
          </div>
        )}
      </Modal>
    </div>
  );
}
