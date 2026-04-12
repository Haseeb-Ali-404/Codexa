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
    backgroundColor: isDark ? "hsl(222 47% 10% / 0.95)" : "hsl(0 0% 100% / 0.98)",
    border: isDark ? "1px solid hsl(222 30% 20%)" : "1px solid hsl(214 32% 91%)",
    borderRadius: "12px",
    fontSize: "12px",
    color: isDark ? "hsl(210 40% 98%)" : "hsl(222 47% 11%)",
    boxShadow: "0 10px 40px -10px rgba(0,0,0,0.35)",
  };
}

export function UsageCharts({ rows, isDark }: UsageChartsProps) {
  const axisColor = isDark ? "hsl(215 20% 55%)" : "hsl(215 16% 47%)";
  const gridColor = isDark ? "hsl(222 30% 18% / 0.5)" : "hsl(214 32% 91% / 0.8)";

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

  const tt = chartTooltipStyle(isDark);

  if (rows.length === 0) return null;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className={cn(
          "rounded-2xl border p-4 shadow-sm",
          isDark ? "border-white/10 bg-card/40" : "border-border/80 bg-card/60",
        )}
      >
        <h3 className="text-sm font-semibold text-foreground mb-1">
          Cost by agent
        </h3>
        <p className="text-xs text-muted-foreground mb-3">Share of estimated spend</p>
        <div className="h-[260px] w-full min-h-[220px]">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
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
                formatter={(v: number) => formatUsd(v)}
                contentStyle={tt}
              />
              <Legend
                wrapperStyle={{ fontSize: "11px", paddingTop: 8 }}
                formatter={(value) => (
                  <span className="text-muted-foreground">{value}</span>
                )}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.26 }}
        className={cn(
          "rounded-2xl border p-4 shadow-sm xl:col-span-2",
          isDark ? "border-white/10 bg-card/40" : "border-border/80 bg-card/60",
        )}
      >
        <h3 className="text-sm font-semibold text-foreground mb-1">
          Tokens by agent
        </h3>
        <p className="text-xs text-muted-foreground mb-3">Input vs output</p>
        <div className="h-[280px] w-full min-h-[240px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={tokenData} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
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
                formatter={(v: number) => formatCompactNumber(v)}
                contentStyle={tt}
              />
              <Legend wrapperStyle={{ fontSize: "11px", paddingTop: 4 }} />
              <Bar
                dataKey="input"
                name="Input"
                fill="#06b6d4"
                radius={[4, 4, 0, 0]}
                maxBarSize={36}
              />
              <Bar
                dataKey="output"
                name="Output"
                fill="#8b5cf6"
                radius={[4, 4, 0, 0]}
                maxBarSize={36}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.32 }}
        className={cn(
          "rounded-2xl border p-4 shadow-sm xl:col-span-3",
          isDark ? "border-white/10 bg-card/40" : "border-border/80 bg-card/60",
        )}
      >
        <h3 className="text-sm font-semibold text-foreground mb-1">
          Requests by agent
        </h3>
        <p className="text-xs text-muted-foreground mb-3">Call volume per agent</p>
        <div className="h-[260px] w-full min-h-[220px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={requestData} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
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
                formatter={(v: number) => formatCompactNumber(v)}
                contentStyle={tt}
              />
              <Bar
                dataKey="requests"
                name="Requests"
                fill="#0891b2"
                radius={[6, 6, 0, 0]}
                maxBarSize={48}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </motion.div>
    </div>
  );
}
