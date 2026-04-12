import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, RefreshCw, X } from "lucide-react";
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
  const pulse = isDark ? "bg-white/[0.06]" : "bg-muted";
  return (
    <div className="space-y-6 animate-pulse">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className={cn("h-28 rounded-2xl border", pulse, isDark ? "border-white/10" : "border-border")}
          />
        ))}
      </div>
      <div className={cn("h-64 rounded-2xl border", pulse, isDark ? "border-white/10" : "border-border")} />
      <div className={cn("h-72 rounded-2xl border", pulse, isDark ? "border-white/10" : "border-border")} />
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
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-[200] bg-black/55 backdrop-blur-md"
            onClick={onClose}
          />
          <div className="fixed inset-0 z-[201] flex items-center justify-center p-4 pointer-events-none">
            <motion.div
              key="usage-panel"
              role="dialog"
              aria-modal="true"
              aria-labelledby="usage-modal-title"
              initial={{ opacity: 0, scale: 0.96, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 12 }}
              transition={{ type: "spring", damping: 28, stiffness: 320 }}
              className={cn(
                "pointer-events-auto w-full max-w-5xl max-h-[min(92vh,900px)] flex flex-col overflow-hidden rounded-2xl border shadow-2xl shadow-black/25",
                isDark
                  ? "border-white/10 bg-[#0c0e12]/95 text-foreground"
                  : "border-border/80 bg-background/95 text-foreground",
              )}
              onClick={(e) => e.stopPropagation()}
            >
              <header
                className={cn(
                  "flex shrink-0 items-start justify-between gap-4 px-6 py-5 border-b",
                  isDark ? "border-white/10 bg-white/[0.02]" : "border-border bg-muted/20",
                )}
              >
                <div>
                  <h2
                    id="usage-modal-title"
                    className="text-xl font-semibold tracking-tight"
                  >
                    Usage analytics
                  </h2>
                  <p className="text-sm text-muted-foreground mt-1">
                    LLM requests, tokens, and estimated cost for this server session.
                  </p>
                  {updatedAt && !loading && (
                    <p className="text-xs text-muted-foreground mt-2 tabular-nums">
                      Last updated{" "}
                      {updatedAt.toLocaleTimeString(undefined, {
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                      })}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="rounded-xl"
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
                    className="rounded-xl shrink-0"
                    onClick={onClose}
                    aria-label="Close"
                  >
                    <X className="h-5 w-5" />
                  </Button>
                </div>
              </header>

              <div className="relative flex-1 overflow-y-auto overscroll-contain px-6 py-6 scrollbar-thin">
                {loading && !payload ? (
                  <UsageSkeleton isDark={isDark} />
                ) : error ? (
                  <div
                    className={cn(
                      "flex flex-col items-center justify-center gap-3 rounded-2xl border py-16 px-6 text-center",
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
                  <div className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed py-20 px-6 text-center border-border/80">
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
                  <div className="space-y-8">
                    <UsageSummaryCards totals={totals} isDark={isDark} />
                    <UsageCharts rows={rows} isDark={isDark} />
                    <div>
                      <h3 className="text-sm font-semibold text-foreground mb-3">
                        Breakdown by agent
                      </h3>
                      <UsageTable rows={rows} isDark={isDark} />
                    </div>
                  </div>
                )}

                {loading && payload ? (
                  <div className="absolute inset-0 z-10 bg-background/50 backdrop-blur-[2px] flex items-center justify-center pointer-events-none">
                    <RefreshCw className="h-8 w-8 animate-spin text-primary opacity-90" />
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
