import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, BarChart3, Clock3, RefreshCw, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { API_BASE } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { UsageSummaryCards } from "./UsageSummaryCards";
import { UsageTable } from "./UsageTable";
import { UsageCharts } from "./UsageCharts";
import {
  computeTotals,
  transformUsageData,
  type UsageApiResponse,
} from "./usageUtils";

interface UsageModalProps {
  open: boolean;
  onClose: () => void;
  isDark: boolean;
}

function UsageSkeleton({ isDark }: { isDark: boolean }) {
  const pulse = isDark ? "bg-white/[0.07]" : "bg-muted";
  return (
    <div className="space-y-6 animate-pulse">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className={cn("h-32 rounded-3xl border shadow-sm", pulse, isDark ? "border-white/10" : "border-border")}
          />
        ))}
      </div>
      <div className={cn("h-80 rounded-3xl border shadow-sm", pulse, isDark ? "border-white/10" : "border-border")} />
      <div className={cn("h-72 rounded-3xl border shadow-sm", pulse, isDark ? "border-white/10" : "border-border")} />
    </div>
  );
}

export function UsageModal({ open, onClose, isDark }: UsageModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [payload, setPayload] = useState<UsageApiResponse | null>(null);

  const fetchUsage = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/metrics/usage`);
      const data = (await res.json()) as UsageApiResponse;
      if (!res.ok || !data.ok) {
        throw new Error(
          typeof (data as { detail?: string }).detail === "string"
            ? (data as { detail: string }).detail
            : "Failed to load usage",
        );
      }
      setPayload(data);
      setUpdatedAt(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error");
      setPayload(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      void fetchUsage();
    }
  }, [open, fetchUsage]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (open) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = prev;
      };
    }
  }, [open]);

  const rows = transformUsageData(payload?.by_agent);
  const totals = computeTotals(rows);

  const modal = (
    <AnimatePresence>
      {open ? (
        <>
          <motion.div
            key="usage-backdrop"
            role="presentation"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="fixed inset-0 z-[200] bg-[radial-gradient(circle_at_75%_15%,hsl(var(--primary)/0.24),transparent_28%),radial-gradient(circle_at_20%_80%,rgba(6,182,212,0.16),transparent_30%),rgba(0,0,0,0.68)] backdrop-blur-lg"
            onClick={onClose}
          />
          <div className="fixed inset-0 z-[201] flex items-center justify-center p-3 sm:p-5 pointer-events-none">
            <motion.div
              key="usage-panel"
              role="dialog"
              aria-modal="true"
              aria-labelledby="usage-modal-title"
              initial={{ opacity: 0, scale: 0.94, y: 22 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 16 }}
              transition={{ type: "spring", damping: 26, stiffness: 280 }}
              className={cn(
                "pointer-events-auto relative w-full max-w-6xl max-h-[min(92vh,940px)] flex flex-col overflow-hidden rounded-[28px] border shadow-2xl",
                isDark
                  ? "border-white/10 bg-[#080a0f]/96 text-foreground shadow-black/45"
                  : "border-border/80 bg-background/96 text-foreground shadow-black/18",
              )}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_82%_0%,hsl(var(--primary)/0.24),transparent_24%),radial-gradient(circle_at_8%_8%,rgba(6,182,212,0.12),transparent_24%)]" />
              <div className="pointer-events-none absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-primary/55 to-transparent" />
              <header
                className={cn(
                  "relative flex shrink-0 items-start justify-between gap-4 border-b px-5 py-5 sm:px-7 sm:py-6",
                  isDark ? "border-white/10 bg-white/[0.025]" : "border-border bg-muted/30",
                )}
              >
                <div className="flex min-w-0 items-start gap-4">
                  <div className="hidden h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-primary/20 bg-primary/10 text-primary shadow-[0_14px_36px_hsl(var(--primary)/0.18)] sm:flex">
                    <BarChart3 className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-primary/80">
                      Server session
                    </p>
                    <h2
                      id="usage-modal-title"
                      className="text-2xl font-semibold tracking-tight sm:text-[28px]"
                    >
                      Usage analytics
                    </h2>
                    <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
                      LLM requests, token volume, and estimated cost across your active agents.
                    </p>
                    {updatedAt && !loading && (
                      <div className="mt-3 inline-flex items-center gap-2 rounded-full border border-border/70 bg-background/40 px-3 py-1 text-xs text-muted-foreground shadow-sm backdrop-blur">
                        <Clock3 className="h-3.5 w-3.5" />
                        <span className="tabular-nums">
                          Updated{" "}
                          {updatedAt.toLocaleTimeString(undefined, {
                            hour: "2-digit",
                            minute: "2-digit",
                            second: "2-digit",
                          })}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="rounded-full border border-border/60 bg-background/70 px-4 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md"
                    disabled={loading}
                    onClick={() => void fetchUsage()}
                  >
                    <RefreshCw
                      className={cn("h-4 w-4 mr-2", loading && "animate-spin")}
                    />
                    Refresh
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="rounded-full shrink-0 transition-all duration-200 hover:bg-destructive/10 hover:text-destructive"
                    onClick={onClose}
                    aria-label="Close"
                  >
                    <X className="h-5 w-5" />
                  </Button>
                </div>
              </header>

              <div className="relative flex-1 overflow-y-auto overscroll-contain px-5 py-6 scrollbar-thin sm:px-7 sm:py-7">
                {loading && !payload ? (
                  <UsageSkeleton isDark={isDark} />
                ) : error ? (
                  <div
                    className={cn(
                      "flex flex-col items-center justify-center gap-3 rounded-3xl border py-16 px-6 text-center shadow-sm",
                      isDark ? "border-red-500/20 bg-red-500/5" : "border-destructive/20 bg-destructive/5",
                    )}
                  >
                    <AlertCircle className="h-10 w-10 text-destructive" />
                    <p className="text-sm font-medium text-foreground">{error}</p>
                    <Button variant="secondary" size="sm" onClick={() => void fetchUsage()}>
                      Try again
                    </Button>
                  </div>
                ) : rows.length === 0 ? (
                  <div className="flex flex-col items-center justify-center gap-2 rounded-3xl border border-dashed py-20 px-6 text-center border-border/80 bg-card/40">
                    <p className="text-sm font-medium text-foreground">No usage yet</p>
                    <p className="text-xs text-muted-foreground max-w-sm">
                      Run a chat or project pipeline to populate metrics. Totals reset when the
                      backend restarts.
                    </p>
                    <Button variant="outline" size="sm" className="mt-2" onClick={() => void fetchUsage()}>
                      Refresh
                    </Button>
                  </div>
                ) : (
                  <motion.div
                    initial="hidden"
                    animate="show"
                    variants={{
                      hidden: {},
                      show: { transition: { staggerChildren: 0.08 } },
                    }}
                    className="space-y-8"
                  >
                    <UsageSummaryCards totals={totals} isDark={isDark} />
                    <UsageCharts rows={rows} isDark={isDark} />
                    <div>
                      <div className="mb-3 flex items-center justify-between gap-3">
                        <div>
                          <h3 className="text-sm font-semibold text-foreground">
                            Breakdown by agent
                          </h3>
                          <p className="mt-0.5 text-xs text-muted-foreground">
                            Sort requests, tokens, and spend by agent.
                          </p>
                        </div>
                      </div>
                      <UsageTable rows={rows} isDark={isDark} />
                    </div>
                  </motion.div>
                )}

                {loading && payload ? (
                  <div className="absolute inset-0 z-10 bg-background/45 backdrop-blur-[3px] flex items-center justify-center pointer-events-none">
                    <div className="rounded-full border border-border/70 bg-background/80 p-4 shadow-xl">
                      <RefreshCw className="h-8 w-8 animate-spin text-primary opacity-90" />
                    </div>
                  </div>
                ) : null}
              </div>
            </motion.div>
          </div>
        </>
      ) : null}
    </AnimatePresence>
  );

  return createPortal(modal, document.body);
}
