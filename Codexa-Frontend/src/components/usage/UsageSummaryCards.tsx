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
  "group relative min-h-[132px] overflow-hidden rounded-3xl border p-5 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-xl";

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
      glow: "group-hover:shadow-cyan-500/15",
      bar: "from-cyan-400 to-cyan-600",
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
      glow: "group-hover:shadow-violet-500/15",
      bar: "from-violet-400 to-indigo-500",
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
      glow: "group-hover:shadow-emerald-500/15",
      bar: "from-emerald-400 to-teal-500",
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      {cards.map((c, i) => (
        <motion.div
          key={c.label}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          whileHover={{ scale: 1.01 }}
          transition={{ delay: i * 0.06, duration: 0.35, ease: "easeOut" }}
          className={cn(
            cardBase,
            "bg-card/75 backdrop-blur-xl",
            c.border,
            c.glow,
          )}
        >
          <div
            className={cn(
              "pointer-events-none absolute inset-0 bg-gradient-to-br opacity-90",
              c.gradient,
            )}
          />
          <div className="pointer-events-none absolute inset-x-5 top-0 h-px bg-gradient-to-r from-transparent via-white/35 to-transparent opacity-70" />
          <div className="pointer-events-none absolute -right-10 -top-10 h-28 w-28 rounded-full bg-white/[0.06] blur-2xl transition-opacity duration-300 group-hover:opacity-100 opacity-60" />
          <div className="relative flex items-start gap-4">
            <div
              className={cn(
                "flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-background/65 dark:bg-white/[0.06] ring-1 ring-border/60 shadow-inner shadow-white/5 transition-transform duration-300 group-hover:scale-105",
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
          <div className="absolute inset-x-5 bottom-4 h-1 overflow-hidden rounded-full bg-foreground/5">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: "72%" }}
              transition={{ delay: 0.18 + i * 0.08, duration: 0.7, ease: "easeOut" }}
              className={cn("h-full rounded-full bg-gradient-to-r", c.bar)}
            />
          </div>
        </motion.div>
      ))}
    </div>
  );
}
