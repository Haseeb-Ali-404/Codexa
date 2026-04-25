import { useState, useEffect, useRef, useCallback } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "@/lib/utils";
import {
  Smartphone,
  Monitor,
  Tablet,
  RefreshCw,
  ExternalLink,
  X,
  CheckCircle2,
  Loader2,
  AlertCircle,
  RotateCcw,
  Wifi,
  WifiOff,
  Globe,
  Lock,
  ArrowLeft,
  ArrowRight,
  Zap,
  Clock,
  Package,
  Shield,
  Rocket,
} from "lucide-react";

type DeviceMode = "desktop" | "tablet" | "mobile";
export type ExecutionMode = "local" | "docker";

interface ServerState {
  phase: "idle" | "starting" | "ready" | "error";
  step: string | null;
  steps_done: string[];
  step_labels: Record<string, string>;
  step_order: string[];
  error: string | null;
  frontend_url: string | null;
  backend_url: string | null;
  elapsed: number | null;
  started_at: number | null;
  project_id: string | null;
  execution_mode?: ExecutionMode;
  logs: string[];
}

interface PreviewPanelProps {
  isOpen: boolean;
  onClose: () => void;
  previewUrl: string;
  projectId?: string;
  onUrlReady?: (url: string) => void;
}

const API_BASE = "http://localhost:8000";

function ElapsedTimer({ startedAt }: { startedAt: number | null }) {
  const [secs, setSecs] = useState(0);

  useEffect(() => {
    if (!startedAt) return;
    const tick = () => setSecs(Math.floor(Date.now() / 1000 - startedAt));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [startedAt]);

  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return <span>{m > 0 ? `${m}m ` : ""}{String(s).padStart(2, "0")}s</span>;
}

interface ExecutionModeModalProps {
  isOpen: boolean;
  selectedMode: ExecutionMode;
  isSubmitting?: boolean;
  onClose: () => void;
  onSelect: (mode: ExecutionMode) => void;
  onConfirm: (mode: ExecutionMode) => void;
}

export function ExecutionModeModal({
  isOpen,
  selectedMode,
  isSubmitting = false,
  onClose,
  onSelect,
  onConfirm,
}: ExecutionModeModalProps) {
  const options = [
    {
      mode: "local" as ExecutionMode,
      title: "Run Locally",
      icon: Monitor,
      accent: "from-sky-500/20 via-sky-500/8 to-transparent",
      ring: "border-sky-500/25",
      badge: "text-sky-300 border-sky-400/20 bg-sky-500/10",
      description: "Faster startup and uses the tools already installed on your machine.",
      bullets: ["Faster startup", "Uses your system environment"],
      cta: "Run Locally",
    },
    {
      mode: "docker" as ExecutionMode,
      title: "Run in Docker",
      icon: Package,
      accent: "from-amber-500/25 via-orange-500/10 to-transparent",
      ring: "border-amber-500/30",
      badge: "text-amber-200 border-amber-400/20 bg-amber-500/10",
      description: "Run your project in an isolated containerized environment with cleaner dependency boundaries.",
      bullets: ["Isolated environment", "More reliable execution", "Prevents dependency conflicts"],
      cta: "Run in Docker",
      recommended: true,
    },
  ];

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          className="fixed inset-0 z-[120] flex items-center justify-center p-4 sm:p-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div
            className="absolute inset-0 bg-slate-950/70 backdrop-blur-md"
            onClick={isSubmitting ? undefined : onClose}
          />

          <motion.div
            initial={{ opacity: 0, scale: 0.94, y: 24 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 18 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
            className="relative w-full max-w-4xl overflow-hidden rounded-[28px] border border-white/12 bg-[linear-gradient(145deg,rgba(17,24,39,0.96),rgba(15,23,42,0.92))] shadow-[0_30px_120px_rgba(15,23,42,0.55)]"
          >
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(245,158,11,0.14),transparent_34%),radial-gradient(circle_at_bottom_left,rgba(56,189,248,0.12),transparent_30%)]" />
            <div className="relative border-b border-white/8 px-6 py-6 sm:px-8">
              <div className="flex items-start justify-between gap-4">
                <div className="max-w-2xl">
                  <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/6 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.28em] text-white/70">
                    <Rocket className="h-3.5 w-3.5 text-amber-300" />
                    Execution
                  </div>
                  <h2 className="mt-4 text-2xl font-semibold tracking-tight text-white sm:text-[2rem]">
                    Choose Execution Mode
                  </h2>
                  <p className="mt-3 max-w-xl text-sm leading-6 text-slate-300/78">
                    Run your project in a secure and isolated environment using Docker, or run it locally on your machine.
                  </p>
                </div>

                <button
                  onClick={onClose}
                  disabled={isSubmitting}
                  className="rounded-2xl border border-white/10 bg-white/5 p-2 text-slate-300 transition-colors hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                  aria-label="Close execution mode dialog"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            <div className="relative grid gap-4 p-6 sm:grid-cols-2 sm:gap-5 sm:p-8">
              {options.map(({ mode, title, icon: Icon, accent, ring, badge, description, bullets, cta, recommended }) => {
                const active = selectedMode === mode;

                return (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => onSelect(mode)}
                    className={cn(
                      "group relative overflow-hidden rounded-[24px] border px-5 py-5 text-left transition-all duration-300",
                      "bg-white/[0.04] backdrop-blur-sm hover:-translate-y-0.5 hover:bg-white/[0.06]",
                      active ? ring : "border-white/10",
                    )}
                  >
                    <div className={cn("pointer-events-none absolute inset-0 bg-gradient-to-br opacity-80", accent)} />
                    <div className="relative">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex items-center gap-3">
                          <div className={cn(
                            "flex h-12 w-12 items-center justify-center rounded-2xl border",
                            active ? "border-white/18 bg-white/12 text-white" : "border-white/10 bg-black/20 text-slate-200",
                          )}>
                            <Icon className="h-5 w-5" />
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <h3 className="text-lg font-semibold text-white">{title}</h3>
                              {recommended && (
                                <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.22em]", badge)}>
                                  Recommended
                                </span>
                              )}
                            </div>
                            <p className="mt-1 text-sm leading-6 text-slate-300/78">{description}</p>
                          </div>
                        </div>

                        <div className={cn(
                          "flex h-7 w-7 items-center justify-center rounded-full border transition-all",
                          active ? "border-emerald-400/35 bg-emerald-500/12 text-emerald-300" : "border-white/12 bg-black/25 text-transparent",
                        )}>
                          <CheckCircle2 className="h-4 w-4" />
                        </div>
                      </div>

                      <div className="mt-5 space-y-2.5">
                        {bullets.map((bullet) => (
                          <div key={bullet} className="flex items-center gap-2 text-sm text-slate-200/88">
                            <Shield className={cn("h-3.5 w-3.5 shrink-0", recommended ? "text-amber-300" : "text-sky-300")} />
                            <span>{bullet}</span>
                          </div>
                        ))}
                      </div>

                      <div className="mt-6 inline-flex items-center gap-2 rounded-full border border-white/12 bg-black/20 px-3 py-1.5 text-xs font-medium text-white/86">
                        <span>{cta}</span>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>

            <div className="relative flex flex-col gap-3 border-t border-white/8 px-6 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-8">
              <div className="text-xs leading-5 text-slate-400">
                Docker is highlighted because it keeps project dependencies isolated, while local mode remains available for faster iteration.
              </div>
              <div className="flex gap-3">
                <button
                  onClick={onClose}
                  disabled={isSubmitting}
                  className="rounded-2xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-medium text-slate-200 transition-colors hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={() => onConfirm(selectedMode)}
                  disabled={isSubmitting}
                  className={cn(
                    "inline-flex min-w-[180px] items-center justify-center gap-2 rounded-2xl px-4 py-2.5 text-sm font-semibold text-slate-950 transition-all",
                    selectedMode === "docker"
                      ? "bg-[linear-gradient(135deg,#f59e0b,#f97316)] shadow-[0_16px_40px_rgba(249,115,22,0.28)]"
                      : "bg-[linear-gradient(135deg,#38bdf8,#2563eb)] shadow-[0_16px_40px_rgba(37,99,235,0.28)]",
                    isSubmitting && "cursor-wait opacity-80",
                  )}
                >
                  {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Rocket className="h-4 w-4" />}
                  {selectedMode === "docker" ? "Run in Docker" : "Run Locally"}
                </button>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function PreviewPanel({
  isOpen,
  onClose,
  previewUrl,
  projectId,
  onUrlReady,
}: PreviewPanelProps) {
  const [deviceMode, setDeviceMode] = useState<DeviceMode>("desktop");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [iframeLoading, setIframeLoading] = useState(false);
  const [serverState, setServerState] = useState<ServerState | null>(null);
  const [effectiveUrl, setEffectiveUrl] = useState(previewUrl);
  const [sseConnected, setSseConnected] = useState(false);
  const [loadedInMs, setLoadedInMs] = useState<number | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const esRef = useRef<EventSource | null>(null);
  const iframeOpenedAt = useRef<number | null>(null);
  const committedUrlRef = useRef<string>("");

  const applyUrl = useCallback((url: string, notifyParent: boolean) => {
    if (!url || committedUrlRef.current === url) return;
    committedUrlRef.current = url;
    setEffectiveUrl(url);
    setIframeLoading(true);
    iframeOpenedAt.current = Date.now();
    if (notifyParent) onUrlReady?.(url);
  }, [onUrlReady]);

  useEffect(() => {
    if (previewUrl) applyUrl(previewUrl, false);
  }, [previewUrl, applyUrl]);

  useEffect(() => {
    if (!isOpen) return;

    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;

    const connect = () => {
      if (stopped) return;
      esRef.current?.close();
      const es = new EventSource(`${API_BASE}/preview/events`);
      esRef.current = es;

      es.onopen = () => setSseConnected(true);

      es.onmessage = (event) => {
        try {
          const data: ServerState = JSON.parse(event.data);
          setServerState(data);

          if (data.phase === "ready" && data.frontend_url) {
            applyUrl(data.frontend_url, true);
            es.close();
            setSseConnected(false);
          }
        } catch {
          // ignore malformed event payloads
        }
      };

      es.onerror = () => {
        setSseConnected(false);
        es.close();
        if (!stopped) retryTimer = setTimeout(connect, 2000);
      };
    };

    connect();

    return () => {
      stopped = true;
      esRef.current?.close();
      esRef.current = null;
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, [applyUrl, isOpen]);

  useEffect(() => {
    if (!iframeLoading || !effectiveUrl) return;
    const timer = setTimeout(() => setIframeLoading(false), 8000);
    return () => clearTimeout(timer);
  }, [effectiveUrl, iframeLoading]);

  const handleRefresh = useCallback(() => {
    if (!effectiveUrl || isRefreshing) return;
    setIsRefreshing(true);
    setIframeLoading(true);
    iframeOpenedAt.current = Date.now();
    setTimeout(() => {
      if (iframeRef.current) {
        iframeRef.current.src = effectiveUrl;
      }
      setIsRefreshing(false);
    }, 350);
  }, [effectiveUrl, isRefreshing]);

  useEffect(() => {
    if (!isOpen || !projectId) return;

    let refreshTimer: ReturnType<typeof setTimeout> | null = null;
    let disposed = false;

    const handleRuntimeMessage = (event: MessageEvent) => {
      const payload = event.data;
      if (!payload || payload.source !== "codexa-preview-monitor") return;
      if (payload.kind !== "issues" || !Array.isArray(payload.issues) || payload.issues.length === 0) {
        return;
      }
      if (iframeRef.current?.contentWindow && event.source !== iframeRef.current.contentWindow) {
        return;
      }

      void fetch(`${API_BASE}/preview/runtime-report/${projectId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode: serverState?.execution_mode ?? "local",
          href: payload.href,
          issues: payload.issues,
        }),
      })
        .then(async (response) => {
          if (!response.ok) return null;
          return response.json();
        })
        .then((data) => {
          if (!data || disposed || !(data.restarting || data.files_fixed > 0)) return;
          if (refreshTimer) clearTimeout(refreshTimer);
          setIframeLoading(true);
          refreshTimer = setTimeout(() => {
            if (!disposed) handleRefresh();
          }, 1800);
        })
        .catch(() => undefined);
    };

    window.addEventListener("message", handleRuntimeMessage);
    return () => {
      disposed = true;
      window.removeEventListener("message", handleRuntimeMessage);
      if (refreshTimer) clearTimeout(refreshTimer);
    };
  }, [handleRefresh, isOpen, projectId, serverState?.execution_mode]);

  const handleRetry = useCallback(async () => {
    if (!projectId) return;
    setEffectiveUrl("");
    setServerState(null);
    setLoadedInMs(null);
    try {
      await fetch(`${API_BASE}/preview/start/${projectId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: serverState?.execution_mode ?? "local" }),
      });
    } catch {
      // SSE will surface any retry failure
    }
  }, [projectId, serverState?.execution_mode]);

  const handleOpenExternal = useCallback(() => {
    if (effectiveUrl) window.open(effectiveUrl, "_blank");
  }, [effectiveUrl]);

  if (!isOpen) return null;

  const phase = serverState?.phase ?? (effectiveUrl ? "ready" : "idle");
  const executionMode = serverState?.execution_mode ?? "local";
  const isLoading = phase === "starting";
  const isIdle = phase === "idle" && !effectiveUrl;
  const isError = phase === "error";
  const stepOrder = serverState?.step_order ?? [];
  const stepLabels = serverState?.step_labels ?? {};
  const stepsDone = serverState?.steps_done ?? [];
  const currentStep = serverState?.step;
  const progress = stepOrder.length > 0
    ? Math.round((stepsDone.length / stepOrder.length) * 100)
    : 0;
  const modeBadgeClass = executionMode === "docker"
    ? "bg-amber-500/10 text-amber-300 border-amber-400/20"
    : "bg-sky-500/10 text-sky-300 border-sky-400/20";
  const modeLabel = executionMode === "docker" ? "Docker" : "Local";

  return (
    <div className="h-full flex flex-col bg-[hsl(var(--background)/0.98)] border-l border-border/50 relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-primary/3 via-transparent to-accent/3" />
      <div className="pointer-events-none absolute inset-0 opacity-[0.03] [background-image:radial-gradient(rgba(255,255,255,0.8)_0.6px,transparent_0.6px)] [background-size:20px_20px]" />

      <div className="relative z-10 flex items-center justify-between px-4 py-2.5 border-b border-border/50 bg-card/70 backdrop-blur-sm shrink-0">
        <div className="flex items-center gap-2.5">
          <div className={cn(
            "w-2 h-2 rounded-full shrink-0 transition-colors duration-500",
            isError ? "bg-red-500" : isLoading ? "bg-amber-400 animate-pulse" : isIdle ? "bg-muted-foreground/30" : "bg-emerald-500 animate-pulse",
          )} />
          <span className="text-sm font-semibold tracking-tight">Preview</span>
          <span className={cn(
            "text-[10px] font-semibold px-2 py-0.5 rounded-full border tracking-wide",
            isError ? "bg-red-500/10 text-red-400 border-red-500/20" : isLoading ? "bg-amber-400/10 text-amber-400 border-amber-400/20" : isIdle ? "bg-muted/30 text-muted-foreground/50 border-border/30" : "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
          )}>
            {isError ? "Failed" : isLoading ? "Building" : isIdle ? "Idle" : "Live"}
          </span>
          <span className={cn(
            "text-[10px] font-semibold px-2 py-0.5 rounded-full border tracking-wide",
            modeBadgeClass,
          )}>
            {modeLabel}
          </span>
        </div>

        <div className="flex items-center gap-1">
          <div
            title={
              sseConnected
                ? "Build stream connected"
                : "Reconnecting..."
            }
            className="p-1.5"
          >
            {sseConnected
              ? <Wifi className="w-3.5 h-3.5 text-emerald-500" />
              : <WifiOff className="w-3.5 h-3.5 text-muted-foreground/40" />}
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary/70 transition-all duration-200"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {!isLoading && !isError && !isIdle && (
        <div className="relative z-10 flex items-center gap-1.5 px-3 py-2 border-b border-border/40 bg-card/50 backdrop-blur-sm shrink-0">
          <div className="flex items-center">
            <button className="p-1.5 rounded-md text-muted-foreground/30 cursor-default">
              <ArrowLeft className="w-3.5 h-3.5" />
            </button>
            <button className="p-1.5 rounded-md text-muted-foreground/30 cursor-default">
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={handleRefresh}
              className={cn(
                "p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary/70 transition-all duration-200",
                isRefreshing && "animate-spin text-primary",
              )}
              title="Refresh"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="flex-1 flex items-center gap-1.5 h-7 px-2.5 rounded-lg bg-secondary/50 border border-border/50 text-[11px] text-muted-foreground font-mono overflow-hidden">
            <Lock className="w-2.5 h-2.5 shrink-0 text-emerald-500" />
            <span className="truncate">{effectiveUrl || "-"}</span>
          </div>

          <div className="flex items-center gap-0.5 p-0.5 rounded-lg bg-secondary/50 border border-border/40">
            {([
              { mode: "desktop" as DeviceMode, icon: Monitor },
              { mode: "tablet" as DeviceMode, icon: Tablet },
              { mode: "mobile" as DeviceMode, icon: Smartphone },
            ] as const).map(({ mode, icon: Icon }) => (
              <button
                key={mode}
                onClick={() => setDeviceMode(mode)}
                className={cn(
                  "p-1.5 rounded-md transition-all duration-200",
                  deviceMode === mode
                    ? "bg-primary text-primary-foreground shadow-sm shadow-primary/30"
                    : "text-muted-foreground hover:text-foreground hover:bg-secondary/80",
                )}
                title={mode}
              >
                <Icon className="w-3.5 h-3.5" />
              </button>
            ))}
          </div>

          <button
            onClick={handleOpenExternal}
            disabled={!effectiveUrl}
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary/70 transition-all duration-200 disabled:opacity-30"
            title="Open in new tab"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      <div className="flex-1 relative overflow-hidden">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center p-6 z-20 bg-background/95 backdrop-blur-sm">
            <div className="w-full max-w-[300px] space-y-4">
              <div className="rounded-2xl border border-border/60 bg-card shadow-2xl shadow-black/25 overflow-hidden">
                <div className="px-5 py-4 border-b border-border/40 bg-gradient-to-r from-primary/8 to-accent/5">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-lg shadow-primary/30 shrink-0">
                      <Zap className="w-4 h-4 text-white" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-semibold">Building preview</p>
                      <p className="text-[11px] text-muted-foreground flex items-center gap-1.5 mt-0.5">
                        <Clock className="w-3 h-3 shrink-0" />
                        <ElapsedTimer startedAt={serverState?.started_at ?? null} />
                      </p>
                      <p className="mt-1 text-[11px] text-muted-foreground/70">
                        {executionMode === "docker"
                          ? "Containerized isolated execution"
                          : "Running on your local machine"}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="px-5 py-4 space-y-3">
                  {(stepOrder.length > 0 ? stepOrder : ["init", "copying", "dependencies", "start_backend", "start_frontend"]).map((stepId) => {
                    const done = stepsDone.includes(stepId);
                    const active = !done && currentStep === stepId;
                    const label = stepLabels[stepId] ?? stepId.replace(/_/g, " ");

                    return (
                      <div key={stepId} className="flex items-center gap-3">
                        <div className={cn(
                          "w-5 h-5 rounded-full flex items-center justify-center shrink-0 transition-all duration-300",
                          done ? "bg-emerald-500/15" : active ? "bg-primary/15" : "bg-muted/40",
                        )}>
                          {done ? (
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                          ) : active ? (
                            <Loader2 className="w-3.5 h-3.5 text-primary animate-spin" />
                          ) : (
                            <div className="w-1.5 h-1.5 rounded-full bg-muted-foreground/25" />
                          )}
                        </div>
                        <span className={cn(
                          "text-[12px] transition-colors duration-300",
                          done ? "text-emerald-500" : active ? "text-foreground font-medium" : "text-muted-foreground/40",
                        )}>
                          {label}
                        </span>
                      </div>
                    );
                  })}
                </div>

                <div className="px-5 pb-5">
                  <div className="h-1.5 w-full rounded-full bg-muted/50 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-primary to-accent transition-all duration-700 ease-out"
                      style={{ width: `${Math.max(progress, 3)}%` }}
                    />
                  </div>
                  <div className="flex items-center justify-between mt-1.5">
                    <span className="text-[10px] text-muted-foreground/60">
                      {stepsDone.length} of {stepOrder.length || "?"} steps
                    </span>
                    <span className="text-[10px] text-muted-foreground/60">{progress}%</span>
                  </div>
                </div>
              </div>

              <p className="text-center text-[11px] text-muted-foreground/50 px-2">
                First run installs packages. Later runs should reuse cached dependencies and start much faster.
              </p>
            </div>
          </div>
        )}

        {isError && (
          <div className="absolute inset-0 flex items-center justify-center p-6 z-20 bg-background/95 backdrop-blur-sm">
            <div className="w-full max-w-[300px]">
              <div className="rounded-2xl border border-red-500/20 bg-card shadow-2xl overflow-hidden">
                <div className="px-5 py-4 border-b border-red-500/15 bg-red-500/5">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-xl bg-red-500/15 flex items-center justify-center shrink-0">
                      <AlertCircle className="w-4 h-4 text-red-400" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold">Build failed</p>
                      {serverState?.elapsed != null && (
                        <p className="text-[11px] text-muted-foreground mt-0.5">
                          After {Math.round(serverState.elapsed)}s
                        </p>
                      )}
                    </div>
                  </div>
                </div>

                <div className="px-5 py-4">
                  <p className="text-[12px] text-muted-foreground leading-relaxed line-clamp-5">
                    {serverState?.error ?? "An unexpected error occurred during the build."}
                  </p>
                </div>

                <div className="px-5 pb-5">
                  {projectId && (
                    <button
                      onClick={handleRetry}
                      className="w-full flex items-center justify-center gap-1.5 py-2 rounded-xl bg-gradient-to-r from-primary to-accent text-primary-foreground text-[12px] font-medium shadow-md shadow-primary/20 hover:opacity-90 transition-all duration-200"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                      Retry
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {isIdle && (
          <div className="absolute inset-0 flex items-center justify-center p-6 z-20 bg-background/95 backdrop-blur-sm">
            <div className="flex flex-col items-center gap-3 text-center">
              <div className="w-12 h-12 rounded-2xl bg-muted/50 flex items-center justify-center">
                <Monitor className="w-5 h-5 text-muted-foreground/40" />
              </div>
              <p className="text-sm font-medium text-muted-foreground/70">No preview running</p>
              <p className="text-[11px] text-muted-foreground/40 max-w-[200px]">
                Generate or open a project to start the live preview
              </p>
            </div>
          </div>
        )}

        <div className={cn(
          "h-full w-full flex items-start justify-center p-3",
          (isLoading || isError || isIdle) && "invisible pointer-events-none",
        )}>
          <div className={cn(
            "h-full mx-auto rounded-xl border border-border/30 shadow-2xl shadow-black/15 overflow-hidden bg-white transition-all duration-500",
            deviceMode === "desktop" && "w-full",
            deviceMode === "tablet" && "max-w-[768px] w-full",
            deviceMode === "mobile" && "max-w-[390px] w-full",
          )}>
            <div className="h-8 bg-secondary/40 border-b border-border/30 flex items-center px-3 gap-2 shrink-0">
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-red-400/60" />
                <div className="w-2.5 h-2.5 rounded-full bg-yellow-400/60" />
                <div className="w-2.5 h-2.5 rounded-full bg-green-400/60" />
              </div>
              <div className="flex-1 mx-2 h-5 rounded bg-background/60 border border-border/30 flex items-center px-2 gap-1.5 overflow-hidden">
                <Globe className="w-2.5 h-2.5 text-muted-foreground/40 shrink-0" />
                <span className="text-[10px] text-muted-foreground/50 font-mono truncate">
                  {effectiveUrl || ""}
                </span>
              </div>
            </div>

            <div className="relative w-full h-[calc(100%-2rem)]">
              {iframeLoading && effectiveUrl && (
                <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10">
                  <Loader2 className="w-5 h-5 text-primary animate-spin" />
                </div>
              )}
              <iframe
                ref={iframeRef}
                id="codexa-preview-iframe"
                src={effectiveUrl || undefined}
                sandbox="allow-scripts allow-same-origin allow-forms allow-modals allow-popups allow-popups-to-escape-sandbox"
                className="w-full h-full border-none bg-white"
                onLoad={() => {
                  setIframeLoading(false);
                  if (iframeOpenedAt.current) {
                    setLoadedInMs(Date.now() - iframeOpenedAt.current);
                    iframeOpenedAt.current = null;
                  }
                }}
              />
            </div>
          </div>
        </div>
      </div>

      <div className="relative z-10 px-4 py-2 border-t border-border/40 bg-card/50 backdrop-blur-sm flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <div className={cn(
              "w-1.5 h-1.5 rounded-full",
              isError ? "bg-red-500" : isLoading ? "bg-amber-400 animate-pulse" : isIdle ? "bg-muted-foreground/30" : "bg-emerald-500",
            )} />
            <span>
              {isError
                ? "Build failed"
                : isLoading
                  ? "Building..."
                  : isIdle
                    ? "No project loaded"
                    : "Dev server running"}
            </span>
          </div>

          {serverState?.backend_url && !isLoading && !isError && (
            <span className="text-muted-foreground/50">
              API <span className="font-mono text-muted-foreground">:{new URL(serverState.backend_url).port}</span>
            </span>
          )}
        </div>

        <span className="text-[11px] text-muted-foreground/70">
          {serverState?.phase === "ready" && serverState.elapsed != null
            ? `Built in ${serverState.elapsed < 60
              ? `${Math.round(serverState.elapsed)}s`
              : `${Math.floor(serverState.elapsed / 60)}m ${Math.round(serverState.elapsed % 60)}s`}`
            : loadedInMs != null
              ? `Loaded in ${loadedInMs < 1000 ? `${loadedInMs}ms` : `${(loadedInMs / 1000).toFixed(1)}s`}`
              : ""}
        </span>
      </div>
    </div>
  );
}
