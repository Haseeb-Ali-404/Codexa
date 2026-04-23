import { motion } from "framer-motion";
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import { cn } from "@/lib/utils";
import type { AgentUsageRow } from "./usageUtils";
import { CHART_PALETTE, formatCompactNumber, formatUsd } from "./usageUtils";

interface UsageChartsProps {
  rows: AgentUsageRow[];
  isDark: boolean;
}

function chartTooltipStyle(isDark: boolean) {
  return {
    backgroundColor: isDark ? "hsl(228 24% 12% / 0.84)" : "hsl(0 0% 100% / 0.9)",
    border: isDark ? "1px solid hsl(255 80% 76% / 0.24)" : "1px solid hsl(214 32% 88%)",
    borderRadius: "16px",
    fontSize: "12px",
    color: isDark ? "hsl(210 40% 98%)" : "hsl(222 47% 11%)",
    boxShadow: isDark
      ? "0 20px 60px -18px rgba(0,0,0,0.62), 0 0 0 1px rgba(255,255,255,0.04) inset"
      : "0 18px 50px -20px rgba(15,23,42,0.2), 0 0 0 1px rgba(255,255,255,0.55) inset",
    backdropFilter: "blur(16px)",
    WebkitBackdropFilter: "blur(16px)",
  };
}

function UsageChartTooltip({
  active,
  payload,
  label,
  isDark,
  valueFormatter,
}: {
  active?: boolean;
  payload?: Array<{ name?: string; value?: number; color?: string; payload?: { name?: string } }>;
  label?: string;
  isDark: boolean;
  valueFormatter: (value: number) => string;
}) {
  if (!active || !payload || payload.length === 0) return null;

  const title = label || payload[0]?.payload?.name || payload[0]?.name || "";

  return (
    <div
      style={chartTooltipStyle(isDark)}
      className="min-w-[170px] px-3.5 py-3"
    >
      <p className="mb-2 text-xs font-semibold tracking-wide text-foreground/95">
        {title}
      </p>
      <div className="space-y-1.5">
        {payload.map((entry, index) => (
          <div key={`${entry.name ?? "item"}-${index}`} className="flex items-center justify-between gap-4 text-xs">
            <div className="flex items-center gap-2">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: entry.color || CHART_PALETTE[index % CHART_PALETTE.length] }}
              />
              <span className="text-foreground/85">{entry.name}</span>
            </div>
            <span className="font-semibold tabular-nums text-foreground">
              {valueFormatter(Number(entry.value) || 0)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

const chartPanelBase =
  "group relative overflow-hidden rounded-3xl border p-5 shadow-sm transition-all duration-300 hover:-translate-y-0.5 hover:shadow-xl";

const chartGlow =
  "pointer-events-none absolute inset-0 opacity-80 bg-[radial-gradient(circle_at_top_right,hsl(var(--primary)/0.14),transparent_38%),linear-gradient(180deg,rgba(255,255,255,0.035),transparent_34%)]";

export function UsageCharts({ rows, isDark }: UsageChartsProps) {
  const axisColor = isDark ? "hsl(215 20% 55%)" : "hsl(215 16% 47%)";
  const gridColor = isDark ? "hsl(222 30% 24% / 0.5)" : "hsl(214 32% 91% / 0.8)";
  const cursorFill = isDark ? "rgba(255,255,255,0.045)" : "rgba(15,23,42,0.045)";

  const costData = rows.map((r) => ({
    name: r.displayName,
    value: r.cost,
  }));

  const tokenData = rows.map((r) => ({
    name: r.displayName,
    input: r.input_tokens,
    output: r.output_tokens,
  }));

  const requestData = rows.map((r) => ({
    name: r.displayName,
    requests: r.requests,
  }));

  if (rows.length === 0) return null;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2, duration: 0.4, ease: "easeOut" }}
        className={cn(
          chartPanelBase,
          isDark ? "border-white/10 bg-card/55 hover:shadow-cyan-500/10" : "border-border/80 bg-card/80",
        )}
      >
        <div className={chartGlow} />
        <div className="relative">
          <h3 className="text-sm font-semibold text-foreground mb-1">
            Cost by agent
          </h3>
          <p className="text-xs text-muted-foreground mb-4">Share of estimated spend</p>
        </div>
        <div className={cn("relative h-[280px] w-full min-h-[230px] rounded-2xl p-2", isDark ? "bg-black/10" : "bg-muted/30")}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart style={{ background: "transparent" }}>
              <Pie
                data={costData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={52}
                outerRadius={88}
                paddingAngle={2}
                strokeWidth={0}
                animationDuration={700}
              >
                {costData.map((_, i) => (
                  <Cell
                    key={i}
                    fill={CHART_PALETTE[i % CHART_PALETTE.length]}
                    className="outline-none"
                  />
                ))}
              </Pie>
              <Tooltip
                content={({ active, payload, label }) => (
                  <UsageChartTooltip
                    active={active}
                    payload={payload as Array<{ name?: string; value?: number; color?: string; payload?: { name?: string } }>}
                    label={label as string}
                    isDark={isDark}
                    valueFormatter={(value) => formatUsd(value)}
                  />
                )}
                cursor={{ fill: cursorFill }}
              />
              <Legend
                wrapperStyle={{ fontSize: "11px", paddingTop: 8 }}
                formatter={(value) => (
                  <span className="font-medium text-foreground/80">{value}</span>
                )}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.26, duration: 0.4, ease: "easeOut" }}
        className={cn(
          chartPanelBase,
          "xl:col-span-2",
          isDark ? "border-white/10 bg-card/55 hover:shadow-violet-500/10" : "border-border/80 bg-card/80",
        )}
      >
        <div className={chartGlow} />
        <div className="relative">
          <h3 className="text-sm font-semibold text-foreground mb-1">
            Tokens by agent
          </h3>
          <p className="text-xs text-muted-foreground mb-4">Input vs output</p>
        </div>
        <div className={cn("relative h-[300px] w-full min-h-[250px] rounded-2xl p-2", isDark ? "bg-black/10" : "bg-muted/30")}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={tokenData} margin={{ top: 8, right: 8, left: 0, bottom: 4 }} style={{ background: "transparent" }}>
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
              <XAxis
                dataKey="name"
                tick={{ fill: axisColor, fontSize: 11 }}
                axisLine={{ stroke: gridColor }}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: axisColor, fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v) => formatCompactNumber(v as number)}
              />
              <Tooltip
                content={({ active, payload, label }) => (
                  <UsageChartTooltip
                    active={active}
                    payload={payload as Array<{ name?: string; value?: number; color?: string; payload?: { name?: string } }>}
                    label={label as string}
                    isDark={isDark}
                    valueFormatter={(value) => formatCompactNumber(value)}
                  />
                )}
                cursor={{ fill: cursorFill }}
              />
              <Legend
                wrapperStyle={{ fontSize: "11px", paddingTop: 4 }}
                formatter={(value) => (
                  <span className="font-medium text-foreground/80">{value}</span>
                )}
              />
              <Bar
                dataKey="input"
                name="Input"
                fill="#06b6d4"
                radius={[4, 4, 0, 0]}
                maxBarSize={36}
                animationDuration={700}
              />
              <Bar
                dataKey="output"
                name="Output"
                fill="#8b5cf6"
                radius={[4, 4, 0, 0]}
                maxBarSize={36}
                animationDuration={800}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.32, duration: 0.4, ease: "easeOut" }}
        className={cn(
          chartPanelBase,
          "xl:col-span-3",
          isDark ? "border-white/10 bg-card/55 hover:shadow-cyan-500/10" : "border-border/80 bg-card/80",
        )}
      >
        <div className={chartGlow} />
        <div className="relative">
          <h3 className="text-sm font-semibold text-foreground mb-1">
            Requests by agent
          </h3>
          <p className="text-xs text-muted-foreground mb-4">Call volume per agent</p>
        </div>
        <div className={cn("relative h-[280px] w-full min-h-[230px] rounded-2xl p-2", isDark ? "bg-black/10" : "bg-muted/30")}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={requestData} margin={{ top: 8, right: 8, left: 0, bottom: 4 }} style={{ background: "transparent" }}>
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
              <XAxis
                dataKey="name"
                tick={{ fill: axisColor, fontSize: 11 }}
                axisLine={{ stroke: gridColor }}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: axisColor, fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                allowDecimals={false}
              />
              <Tooltip
                content={({ active, payload, label }) => (
                  <UsageChartTooltip
                    active={active}
                    payload={payload as Array<{ name?: string; value?: number; color?: string; payload?: { name?: string } }>}
                    label={label as string}
                    isDark={isDark}
                    valueFormatter={(value) => formatCompactNumber(value)}
                  />
                )}
                cursor={{ fill: cursorFill }}
              />
              <Bar
                dataKey="requests"
                name="Requests"
                fill="#0891b2"
                radius={[6, 6, 0, 0]}
                maxBarSize={48}
                animationDuration={700}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </motion.div>
    </div>
  );
}
