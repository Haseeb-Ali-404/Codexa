export interface AgentUsageBackend {
  requests: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
}

export interface UsageApiResponse {
  ok: boolean;
  by_agent: Record<string, AgentUsageBackend>;
}

export interface AgentUsageRow {
  name: string;
  displayName: string;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  cost: number;
}

export interface UsageTotals {
  requests: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost: number;
}

const AGENT_LABELS: Record<string, string> = {
  planner: "Planner",
  developer: "Developer",
  debugger: "Debugger",
  classifier: "Classifier",
  integrator: "Integrator",
  architect: "Architect",
  chat: "Chat",
  title: "Title",
  unknown: "Unknown",
};

export function agentDisplayName(key: string): string {
  const k = key.toLowerCase();
  return (
    AGENT_LABELS[k] ??
    key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

export function transformUsageData(
  by_agent: Record<string, AgentUsageBackend> | undefined | null,
): AgentUsageRow[] {
  if (!by_agent || typeof by_agent !== "object") return [];
  return Object.entries(by_agent).map(([name, v]) => ({
    name,
    displayName: agentDisplayName(name),
    requests: Number(v.requests) || 0,
    input_tokens: Number(v.input_tokens) || 0,
    output_tokens: Number(v.output_tokens) || 0,
    cost: Number(v.estimated_cost_usd) || 0,
  }));
}

export function computeTotals(rows: AgentUsageRow[]): UsageTotals {
  return rows.reduce(
    (acc, r) => ({
      requests: acc.requests + r.requests,
      input_tokens: acc.input_tokens + r.input_tokens,
      output_tokens: acc.output_tokens + r.output_tokens,
      total_tokens: acc.total_tokens + r.input_tokens + r.output_tokens,
      cost: acc.cost + r.cost,
    }),
    {
      requests: 0,
      input_tokens: 0,
      output_tokens: 0,
      total_tokens: 0,
      cost: 0,
    },
  );
}

/** 12000 → 12k, 1_500_000 → 1.5M */
export function formatCompactNumber(n: number): string {
  if (!Number.isFinite(n)) return "0";
  const abs = Math.abs(n);
  if (abs < 1000) return String(Math.round(n));
  if (abs < 1_000_000) {
    const k = n / 1000;
    return `${k >= 10 ? Math.round(k) : Math.round(k * 10) / 10}k`;
  }
  const m = n / 1_000_000;
  return `${m >= 10 ? Math.round(m) : Math.round(m * 10) / 10}M`;
}

/** Currency: min 2 decimals, trim trailing zeros up to 2 */
export function formatUsd(n: number, maxDecimals = 2): string {
  if (!Number.isFinite(n)) return "$0.00";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: maxDecimals,
  }).format(n);
}

export type SortKey = "name" | "requests" | "input_tokens" | "output_tokens" | "cost";
export type SortDir = "asc" | "desc";

export function sortRows(
  rows: AgentUsageRow[],
  key: SortKey,
  dir: SortDir,
): AgentUsageRow[] {
  const mult = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    let cmp = 0;
    if (key === "name") {
      cmp = a.displayName.localeCompare(b.displayName);
    } else {
      cmp = a[key] - b[key];
    }
    return cmp * mult;
  });
}

/** Distinct colors for charts (WCAG-friendly on dark/light backgrounds) */
export const CHART_PALETTE = [
  "#06b6d4",
  "#8b5cf6",
  "#f59e0b",
  "#10b981",
  "#ec4899",
  "#3b82f6",
  "#ef4444",
  "#84cc16",
];
