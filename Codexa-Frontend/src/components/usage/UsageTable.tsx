import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { AgentUsageRow, SortDir, SortKey } from "./usageUtils";
import { formatCompactNumber, formatUsd, sortRows } from "./usageUtils";

interface UsageTableProps {
  rows: AgentUsageRow[];
  isDark: boolean;
}

const COLUMNS: { key: SortKey; label: string; align?: "right" }[] = [
  { key: "name", label: "Agent" },
  { key: "requests", label: "Requests", align: "right" },
  { key: "input_tokens", label: "Input tokens", align: "right" },
  { key: "output_tokens", label: "Output tokens", align: "right" },
  { key: "cost", label: "Cost", align: "right" },
];

export function UsageTable({ rows, isDark }: UsageTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("cost");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const sorted = useMemo(
    () => sortRows(rows, sortKey, sortDir),
    [rows, sortKey, sortDir],
  );

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "name" ? "asc" : "desc");
    }
  };

  const SortIcon = ({ k }: { k: SortKey }) => {
    if (sortKey !== k) {
      return <ArrowUpDown className="ml-1 h-3.5 w-3.5 opacity-40" />;
    }
    return sortDir === "asc" ? (
      <ArrowUp className="ml-1 h-3.5 w-3.5 text-primary" />
    ) : (
      <ArrowDown className="ml-1 h-3.5 w-3.5 text-primary" />
    );
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.15 }}
      className={cn(
        "rounded-2xl border overflow-hidden shadow-sm",
        isDark ? "border-white/10 bg-card/40" : "border-border/80 bg-card/60",
      )}
    >
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr
              className={cn(
                "border-b text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground",
                isDark ? "border-white/10 bg-white/[0.03]" : "border-border bg-muted/30",
              )}
            >
              {COLUMNS.map((col) => (
                <th
                  key={col.key}
                  className={cn(
                    "px-4 py-3",
                    col.align === "right" && "text-right",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => toggleSort(col.key)}
                    className={cn(
                      "inline-flex items-center rounded-md px-1 py-0.5 -mx-1 transition-colors hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
                      col.align === "right" && "ml-auto flex-row-reverse",
                    )}
                  >
                    {col.label}
                    <SortIcon k={col.key} />
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, i) => (
              <tr
                key={row.name}
                className={cn(
                  "border-b last:border-0 transition-colors",
                  isDark
                    ? "border-white/[0.06] hover:bg-white/[0.04]"
                    : "border-border/60 hover:bg-muted/40",
                )}
              >
                <td className="px-4 py-3 font-medium text-foreground">
                  {row.displayName}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
                  {formatCompactNumber(row.requests)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
                  {formatCompactNumber(row.input_tokens)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
                  {formatCompactNumber(row.output_tokens)}
                </td>
                <td className="px-4 py-3 text-right font-medium tabular-nums text-foreground">
                  {formatUsd(row.cost)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </motion.div>
  );
}
