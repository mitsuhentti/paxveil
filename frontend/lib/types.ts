export type Severity = "critical" | "high" | "medium" | "low" | "unknown";
export interface User { id: string; username: string; telegram_id?: number | null }
export interface Dependency { name: string; version: string | null; direct: boolean | null; source: string; marker?: string; status: string }
export interface Finding {
  id: string; aliases: string[]; package: string; version: string; summary: string; severity: Severity;
  cvss: number | null; epss: number | null; epss_date: string | null; kev?: boolean | null; priority: number;
  priority_reasons: string[]; affected: unknown; fixed_versions: string[]; references: Array<string | { url: string; type?: string }>;
  published: string | null; modified: string | null; status: string;
}
export interface GraphNode { id: string; name: string; version: string | null; direct: boolean | null }
export interface Report {
  dependencies: Dependency[]; findings: Finding[]; graph: { nodes: GraphNode[]; edges: Array<{ source: string; target: string }> };
  warnings: string[]; sources: Array<{ name: string; status: string; fetched_at: string | null; error?: string }>;
  stats: { dependencies: number; findings: number; duration_seconds: number };
  completeness: string; environment: { python_version: string; platform: string };
}
export interface Scan { id: string; status: string; created_at: string; report?: Report | null; error?: string | null }
export interface Project { id: string; name: string; created_at: string; watch: boolean; latest_scan: Scan | null }
export interface Job { id: string; status: string; kind: string; result: unknown; error: string | null; attempts: number }
export interface FixSummary { dependencies: number; findings: number; known_vulnerabilities: number }
export interface Strategy { name: string; updates: Array<{ package: string; from: string; to: string }>; before: FixSummary; after: FixSummary | null; conflicts: unknown[]; uncertainties: unknown[]; graph_changes: unknown; reason: string; status: string }
export interface FixResult { strategies: Strategy[]; limitations: string[] }
export interface FireResult { cve: string; status: string; advisories: unknown[]; matches: Array<{ project_id: string; project_name: string; package: string; version: string; status: string; advisory_id: string; path: string[]; fixed_versions: string[]; references: Array<string | { url: string }> }>; limitations: string[] }
export interface Settings { telegram_id: number | null; timezone: string; quiet_start: string | null; quiet_end: string | null; minimum_priority: number; digest: boolean; categories: string[]; upload_python_version: string; upload_platform: "linux" | "windows" | "darwin" }
export interface Notification { id: string; project_id: string; category: string; payload: { project_name: string; finding: Finding }; status: string; created_at: string; attempts: number }

