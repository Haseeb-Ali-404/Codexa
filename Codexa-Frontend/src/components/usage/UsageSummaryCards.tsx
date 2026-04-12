import { motion } from "framer-motion";
import { Activity, Coins, Layers } from "lucide-react";
import { cn } from "@/lib/utils";
import type { UsageTotals } from "./usageUtils";
import { formatCompactNumber, formatUsd } from "./usageUtils";

interface UsageSummaryCardsProps {
  totals: UsageTotals;
  isDark: boolean;
}

const cardBase =
  "relative overflow-hidden rounded-2xl border p-5 shadow-sm transition-shadow duration-300 hover:shadow-md";

export function UsageSummaryCards({ totals, isDark }: UsageSummaryCardsProps) {
  const cards = [
    {
      label: "Total requests",
      value: formatCompactNumber(totals.requests),
      icon: Activity,
      gradient: isDark
        ? "from-cyan-500/20 via-cyan-500/5 to-transparent"
        : "from-cyan-500/15 via-cyan-500/5 to-transparent",
      border: isDark ? "border-cyan-500/20" : "border-cyan-500/25",
      iconClass: "text-cyan-500",
    },
    {
      label: "Total tokens",
      value: formatCompactNumber(totals.total_tokens),
      sub: `${formatCompactNumber(totals.input_tokens)} in · ${formatCompactNumber(totals.output_tokens)} out`,
      icon: Layers,
      gradient: isDark
        ? "from-violet-500/20 via-violet-500/5 to-transparent"
        : "from-violet-500/15 via-violet-500/5 to-transparent",
      border: isDark ? "border-violet-500/20" : "border-violet-500/25",
      iconClass: "text-violet-500",
    },
    {
      label: "Estimated cost",
      value: formatUsd(totals.cost, 4),
      sub: "USD · session totals",
      icon: Coins,
      gradient: isDark
        ? "from-emerald-500/20 via-emerald-500/5 to-transparent"
        : "from-emerald-500/15 via-emerald-500/5 to-transparent",
      border: isDark ? "border-emerald-500/20" : "border-emerald-500/25",
      iconClass: "text-emerald-500",
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      {cards.map((c, i) => (
        <motion.div
          key={c.label}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.06, duration: 0.35 }}
          className={cn(
            cardBase,
            "bg-card/80 backdrop-blur-sm",
            c.border,
          )}
        >
          <div
            className={cn(
              "pointer-events-none absolute inset-0 bg-gradient-to-br opacity-90",
              c.gradient,
            )}
          />
          <div className="relative flex items-start gap-4">
            <div
              className={cn(
                "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-background/60 dark:bg-white/5 ring-1 ring-border/60",
              )}
            >
              <c.icon className={cn("h-5 w-5", c.iconClass)} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {c.label}
              </p>
              <p className="mt-1 text-2xl font-semibold tracking-tight text-foreground tabular-nums">
                {c.value}
              </p>
              {"sub" in c && c.sub ? (
                <p className="mt-0.5 text-xs text-muted-foreground">{c.sub}</p>
              ) : null}
            </div>
          </div>
        </motion.div>
      ))}
    </div>
  );
}
