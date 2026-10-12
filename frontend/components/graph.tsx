"use client";

import { useMemo, useState } from "react";
import { Search, GitBranch, ZoomIn, ZoomOut, RotateCcw, Info } from "lucide-react";
import type { Report } from "@/lib/types";
import { Empty } from "./ui";

const nodeWidth = 240;
const nodeHeight = 64;

export function DependencyGraph({ report }: { report: Report }) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const { nodes, edges } = report.graph;

  const path = useMemo(() => {
    if (!selected) return [];
    const queue = nodes.filter(node => node.direct).map(node => [node.id]);
    const visited = new Set<string>();
    while (queue.length) {
      const current = queue.shift()!;
      const tail = current[current.length - 1];
      if (tail === selected) return current;
      if (visited.has(tail)) continue;
      visited.add(tail);
      edges.filter(edge => edge.source === tail).forEach(edge => queue.push([...current, edge.target]));
    }
    return [selected];
  }, [nodes, edges, selected]);

  const positions = useMemo(() => {
    const map = new Map<string, { x: number; y: number }>();
    const levels = new Map<string, number>();
    const queue = nodes.filter(node => node.direct).map(node => ({ id: node.id, level: 0 }));
    while (queue.length) {
      const current = queue.shift()!;
      if (levels.has(current.id)) continue;
      levels.set(current.id, current.level);
      edges.filter(edge => edge.source === current.id).forEach(edge => {
        queue.push({ id: edge.target, level: Math.min(current.level + 1, 4) });
      });
    }
    nodes.forEach(node => { if (!levels.has(node.id)) levels.set(node.id, 0); });
    for (let level = 0; level <= 4; level++) {
      const group = nodes.filter(node => levels.get(node.id) === level);
      group.forEach((node, index) => map.set(node.id, { x: 32 + level * 300, y: 32 + index * 96 }));
    }
    return map;
  }, [nodes, edges]);

  const maxX = Math.max(700, ...Array.from(positions.values()).map(position => position.x + nodeWidth + 32));
  const maxY = Math.max(300, ...Array.from(positions.values()).map(position => position.y + nodeHeight + 32));
  const vulnerable = new Set(report.findings.map(finding => `${finding.package}==${finding.version}`));
  const selectedNode = nodes.find(node => node.id === selected);
  const matchingNodes = nodes.filter(node => !query || node.name.toLowerCase().includes(query.toLowerCase())).length;

  if (!nodes.length) {
    return <Empty title="Нет данных для графа" detail="В этом отчёте нет зависимостей, которые можно отобразить." />;
  }

  return (
    <section className="report-section">
      <div className="graph-overview report-title">
        <h2>Граф зависимостей</h2>
        <span className="muted">Пакеты: {nodes.length} · Связи: {edges.length}</span>
      </div>
      <div className="graph-toolbar">
        <label className="search-box">
          <Search size={17} />
          <input
            aria-label="Найти зависимость в графе"
            placeholder="Название пакета"
            value={query}
            onChange={event => setQuery(event.target.value)}
          />
        </label>
        <div className="button-group">
          <button className="icon-button" aria-label="Уменьшить граф" disabled={zoom <= 0.5} onClick={() => setZoom(Math.max(0.5, zoom - 0.2))}>
            <ZoomOut size={18} />
          </button>
          <span className="mono">{Math.round(zoom * 100)}%</span>
          <button className="icon-button" aria-label="Увеличить граф" disabled={zoom >= 2} onClick={() => setZoom(Math.min(2, zoom + 0.2))}>
            <ZoomIn size={18} />
          </button>
          <button
            className="icon-button"
            aria-label="Сбросить масштаб и выбор"
            onClick={() => { setZoom(1); setSelected(null); setQuery(""); }}
          ><RotateCcw size={16} /></button>
        </div>
      </div>
      <p className="form-hint">Нажмите на пакет, чтобы увидеть путь от прямой зависимости.</p>
      {query && matchingNodes === 0 && <p className="graph-empty-note">Пакет с таким названием не найден.</p>}
      <div className="graph-canvas">
        <svg width={maxX * zoom} height={maxY * zoom} viewBox={`0 0 ${maxX} ${maxY}`} role="group" aria-label="Граф зависимостей">
          <defs>
            <marker id="graph-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto">
              <path d="M0 0 10 5 0 10" fill="var(--graph-edge)" />
            </marker>
          </defs>
          {edges.map((edge, index) => {
            const source = positions.get(edge.source);
            const target = positions.get(edge.target);
            if (!source || !target) return null;
            const pathIndex = path.indexOf(edge.source);
            const active = pathIndex >= 0 && path[pathIndex + 1] === edge.target;
            return (
              <path
                key={index}
                d={`M${source.x + nodeWidth} ${source.y + nodeHeight / 2} C${source.x + nodeWidth + 30} ${source.y + nodeHeight / 2}, ${target.x - 30} ${target.y + nodeHeight / 2}, ${target.x} ${target.y + nodeHeight / 2}`}
                fill="none"
                stroke={active ? "var(--accent)" : "var(--graph-edge)"}
                strokeWidth={active ? 2 : 1.3}
                markerEnd="url(#graph-arrow)"
              />
            );
          })}
          {nodes.map(node => {
            const position = positions.get(node.id)!;
            const matches = !query || node.name.toLowerCase().includes(query.toLowerCase());
            const color = vulnerable.has(node.id) ? "var(--danger)" : node.direct ? "var(--accent)" : "var(--graph-edge)";
            const origin = node.direct === null ? "Тип неизвестен" : node.direct ? "Прямая" : "Транзитивная";
            return (
              <g
                key={node.id}
                transform={`translate(${position.x} ${position.y})`}
                className="graph-node"
                opacity={matches ? 1 : 0.25}
                role="button"
                tabIndex={0}
                aria-label={`${node.name} ${node.version || "версия неизвестна"}, ${origin.toLowerCase()}`}
                aria-pressed={selected === node.id}
                onClick={() => setSelected(node.id)}
                onKeyDown={event => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setSelected(node.id);
                  }
                }}
              >
                <rect
                  width={nodeWidth}
                  height={nodeHeight}
                  rx="7"
                  fill="var(--surface)"
                  stroke={selected === node.id ? "var(--text)" : "var(--border)"}
                  strokeWidth={selected === node.id ? 2 : 1}
                />
                <rect x="0" y="14" width="3" height="36" rx="1.5" fill={color} />
                <text x="18" y="27" fill="var(--text)" fontSize="14" fontWeight="600">
                  {node.name.length > 25 ? `${node.name.slice(0, 23)}...` : node.name}
                </text>
                <text x="18" y="48" fill="var(--muted)" fontSize="12">
                  {node.version || "Версия неизвестна"} · {origin}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      {selectedNode && (
        <div className="graph-detail">
          <GitBranch size={20} />
          <div>
            <strong>{selectedNode.name} <span className="mono muted">{selectedNode.version}</span></strong>
            <p className="mono">{path.join(" → ")}</p>
            {path.length === 1 && !selectedNode.direct && (
              <span className="form-hint">Путь от прямой зависимости не подтверждён.</span>
            )}
          </div>
        </div>
      )}
      <div className="graph-legend">
        <span><i className="accent-dot" /> Прямая зависимость</span>
        <span><i className="muted-dot" /> Остальные пакеты</span>
        <span><i className="danger-dot" /> Известная уязвимость</span>
      </div>
      <p className="analysis-note">
        <Info size={16} /> Показаны пакеты из загруженного файла и подтверждённые связи между ними.
        {edges.length === 0 && " Связи в этом отчёте не определены."}
      </p>
    </section>
  );
}
