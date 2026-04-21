import { useState, useEffect, useRef, useCallback } from "react";
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
  Terminal,
  AlertCircle,
  RotateCcw,
  ChevronDown,
  ChevronRight,
  Wifi,
  WifiOff,
  Globe,
  Lock,
  ArrowLeft,
  ArrowRight,
  Zap,
  Clock,
} from "lucide-react";

type DeviceMode = "desktop" | "tablet" | "mobile";

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
  const [showConsole, setShowConsole] = useState(false);
  const [consoleExpanded, setConsoleExpanded] = useState(false);
  const [serverState, setServerState] = useState<ServerState | null>(null);
  const [effectiveUrl, setEffectiveUrl] = useState(previewUrl);
  const [sseConnected, setSseConnected] = useState(false);
  const [loadedInMs, setLoadedInMs] = useState<number | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const consoleEndRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);
  const iframeOpenedAt = useRef<number | null>(null);
  const committedUrlRef = useRef<string>("");

  const _applyUrl = useCallback((url: string, notifyParent: boolean) => {
    if (!url || committedUrlRef.current === url) return;
    committedUrlRef.current = url;
    setEffectiveUrl(url);
    setIframeLoading(true);
    iframeOpenedAt.current = Date.now();
    if (notifyParent) onUrlReady?.(url);
  }, [onUrlReady]); // eslint-disable-line

  // Sync previewUrl prop → internal URL
  useEffect(() => {
    if (previewUrl) _applyUrl(previewUrl, false);
  }, [previewUrl, _applyUrl]);

  // SSE subscription for real-time build status
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
            // _applyUrl is safe to call here — side effects are outside setState
            _applyUrl(data.frontend_url, true);
            es.close();
            setSseConnected(false);
          }
        } catch {
          // ignore JSON parse errors
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
  }, [isOpen, _applyUrl]); // eslint-disable-line

  // Auto-scroll console to bottom
  useEffect(() => {
    if (showConsole) {
      consoleEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [serverState?.logs?.length, showConsole]);

  // Hard timeout: show the iframe after 8s even if onLoad never fires.
  // Prevents the spinner blocking the user when vite dev is slow or onLoad is delayed.
  useEffect(() => {
    if (!iframeLoading || !effectiveUrl) return;
    const timer = setTimeout(() => setIframeLoading(false), 8000);
    return () => clearTimeout(timer);
  }, [iframeLoading, effectiveUrl]);

  const handleRefresh = useCallback(() => {
    if (!effectiveUrl || isRefreshing) return;
    setIsRefreshing(true);
    setIframeLoading(true);
    iframeOpenedAt.current = Date.now();
    setTimeout(() => {
      if (iframeRef.current) iframeRef.current.src = effectiveUrl;
      setIsRefreshing(false);
    }, 350);
  }, [effectiveUrl, isRefreshing]);

  const handleRetry = useCallback(async () => {
    if (!projectId) return;
    setEffectiveUrl("");
    setServerState(null);
    setLoadedInMs(null);
    try {
      await fetch(`${API_BASE}/preview/start/${projectId}`, { method: "POST" });
    } catch {
      // SSE will surface the error
    }
  }, [projectId]);

  const handleOpenExternal = useCallback(() => {
    if (effectiveUrl) window.open(effectiveUrl, "_blank");
  }, [effectiveUrl]);

  if (!isOpen) return null;

  const phase = serverState?.phase ?? (effectiveUrl ? "ready" : "idle");
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

  return (
    <div className="h-full flex flex-col bg-[hsl(var(--background)/0.98)] border-l border-border/50 relative overflow-hidden">

      {/* Ambient gradient */}
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-primary/3 via-transparent to-accent/3" />
      <div className="pointer-events-none absolute inset-0 opacity-[0.03] [background-image:radial-gradient(rgba(255,255,255,0.8)_0.6px,transparent_0.6px)] [background-size:20px_20px]" />

      {/* ── Header ────────────────────────────────────────────────────────── */}
      <div className="relative z-10 flex items-center justify-between px-4 py-2.5 border-b border-border/50 bg-card/70 backdrop-blur-sm shrink-0">
        <div className="flex items-center gap-2.5">
          <div className={cn(
            "w-2 h-2 rounded-full shrink-0 transition-colors duration-500",
            isError   ? "bg-red-500"
            : isLoading ? "bg-amber-400 animate-pulse"
            : isIdle  ? "bg-muted-foreground/30"
            : "bg-emerald-500 animate-pulse",
          )} />
          <span className="text-sm font-semibold tracking-tight">Preview</span>
          <span className={cn(
            "text-[10px] font-semibold px-2 py-0.5 rounded-full border tracking-wide",
            isError   ? "bg-red-500/10 text-red-400 border-red-500/20"
            : isLoading ? "bg-amber-400/10 text-amber-400 border-amber-400/20"
            : isIdle  ? "bg-muted/30 text-muted-foreground/50 border-border/30"
            : "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
          )}>
            {isError ? "Failed" : isLoading ? "Building" : isIdle ? "Idle" : "Live"}
          </span>
        </div>

        <div className="flex items-center gap-1">
          <div
            title={sseConnected ? "Build stream connected" : "Reconnecting…"}
            className="p-1.5"
          >
            {sseConnected
              ? <Wifi className="w-3.5 h-3.5 text-emerald-500" />
              : <WifiOff className="w-3.5 h-3.5 text-muted-foreground/40" />}
          </div>

          <button
            onClick={() => setShowConsole((p) => !p)}
            className={cn(
              "p-1.5 rounded-lg transition-all duration-200",
              showConsole
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:text-foreground hover:bg-secondary/70",
            )}
            title="Build logs"
          >
            <Terminal className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary/70 transition-all duration-200"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* ── Browser toolbar (only when preview is ready) ───────────────── */}
      {!isLoading && !isError && (
        <div className="relative z-10 flex items-center gap-1.5 px-3 py-2 border-b border-border/40 bg-card/50 backdrop-blur-sm shrink-0">
          {/* Nav */}
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

          {/* URL bar */}
          <div className="flex-1 flex items-center gap-1.5 h-7 px-2.5 rounded-lg bg-secondary/50 border border-border/50 text-[11px] text-muted-foreground font-mono overflow-hidden">
            <Lock className="w-2.5 h-2.5 shrink-0 text-emerald-500" />
            <span className="truncate">{effectiveUrl || "—"}</span>
          </div>

          {/* Device mode */}
          <div className="flex items-center gap-0.5 p-0.5 rounded-lg bg-secondary/50 border border-border/40">
            {([
              { mode: "desktop" as DeviceMode, icon: Monitor },
              { mode: "tablet"  as DeviceMode, icon: Tablet },
              { mode: "mobile"  as DeviceMode, icon: Smartphone },
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

      {/* ── Console / Build logs ──────────────────────────────────────────── */}
      {showConsole && (
        <div className={cn(
          "relative z-10 border-b border-border/50 bg-[#0d1117] shrink-0 overflow-hidden",
          consoleExpanded ? "max-h-60" : "max-h-32",
        )}>
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-white/5 sticky top-0 bg-[#0d1117] z-10">
            <span className="text-[10px] font-mono text-emerald-400 uppercase tracking-widest">Build output</span>
            <button
              onClick={() => setConsoleExpanded((p) => !p)}
              className="p-0.5 text-muted-foreground hover:text-foreground transition-colors"
            >
              {consoleExpanded
                ? <ChevronDown className="w-3.5 h-3.5" />
                : <ChevronRight className="w-3.5 h-3.5" />}
            </button>
          </div>
          <div className="overflow-y-auto" style={{ maxHeight: consoleExpanded ? "200px" : "80px" }}>
            {(serverState?.logs ?? []).length === 0 ? (
              <p className="px-3 py-2 text-[11px] font-mono text-muted-foreground/40">
                Waiting for build output…
              </p>
            ) : (
              serverState?.logs.map((line, i) => (
                <div
                  key={i}
                  className="px-3 py-0.5 text-[11px] font-mono text-emerald-300/75 leading-relaxed break-all"
                >
                  {line}
                </div>
              ))
            )}
            <div ref={consoleEndRef} />
          </div>
        </div>
      )}

      {/* ── Main content ─────────────────────────────────────────────────── */}
      <div className="flex-1 relative overflow-hidden">

        {/* LOADING STATE */}
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center p-6 z-20 bg-background/95 backdrop-blur-sm">
            <div className="w-full max-w-[300px] space-y-4">

              {/* Build card */}
              <div className="rounded-2xl border border-border/60 bg-card shadow-2xl shadow-black/25 overflow-hidden">
                {/* Card header */}
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
                    </div>
                  </div>
                </div>

                {/* Steps list */}
                <div className="px-5 py-4 space-y-3">
                  {(stepOrder.length > 0 ? stepOrder : ["init", "copying", "dependencies", "start_backend", "start_frontend"]).map((stepId) => {
                    const done   = stepsDone.includes(stepId);
                    const active = !done && currentStep === stepId;
                    const label  = stepLabels[stepId] ?? stepId.replace(/_/g, " ");

                    return (
                      <div key={stepId} className="flex items-center gap-3">
                        <div className={cn(
                          "w-5 h-5 rounded-full flex items-center justify-center shrink-0 transition-all duration-300",
                          done   ? "bg-emerald-500/15"
                          : active ? "bg-primary/15"
                          : "bg-muted/40",
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
                          done   ? "text-emerald-500"
                          : active ? "text-foreground font-medium"
                          : "text-muted-foreground/40",
                        )}>
                          {label}
                        </span>
                      </div>
                    );
                  })}
                </div>

                {/* Progress bar */}
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
                First run installs packages — later runs skip this and load instantly
              </p>
            </div>
          </div>
        )}

        {/* ERROR STATE */}
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

                <div className="px-5 pb-5 flex gap-2">
                  <button
                    onClick={() => { setShowConsole(true); setConsoleExpanded(true); }}
                    className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl border border-border/60 text-[12px] text-muted-foreground hover:text-foreground hover:bg-secondary/60 transition-all duration-200"
                  >
                    <Terminal className="w-3.5 h-3.5" />
                    Logs
                  </button>
                  {projectId && (
                    <button
                      onClick={handleRetry}
                      className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl bg-gradient-to-r from-primary to-accent text-primary-foreground text-[12px] font-medium shadow-md shadow-primary/20 hover:opacity-90 transition-all duration-200"
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

        {/* IDLE STATE */}
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

        {/* IFRAME — always mounted so it stays alive when toggling console etc. */}
        <div className={cn(
          "h-full w-full flex items-start justify-center p-3",
          (isLoading || isError || isIdle) && "invisible pointer-events-none",
        )}>
          <div className={cn(
            "h-full mx-auto rounded-xl border border-border/30 shadow-2xl shadow-black/15 overflow-hidden bg-white transition-all duration-500",
            deviceMode === "desktop" && "w-full",
            deviceMode === "tablet"  && "max-w-[768px] w-full",
            deviceMode === "mobile"  && "max-w-[390px] w-full",
          )}>
            {/* Mini browser chrome */}
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

            {/* iframe */}
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

      {/* ── Status bar ────────────────────────────────────────────────────── */}
      <div className="relative z-10 px-4 py-2 border-t border-border/40 bg-card/50 backdrop-blur-sm flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <div className={cn(
              "w-1.5 h-1.5 rounded-full",
              isError   ? "bg-red-500"
              : isLoading ? "bg-amber-400 animate-pulse"
              : isIdle  ? "bg-muted-foreground/30"
              : "bg-emerald-500",
            )} />
            <span>
              {isError ? "Build failed" : isLoading ? "Building…" : isIdle ? "No project loaded" : "Dev server running"}
            </span>
          </div>

          {serverState?.backend_url && !isLoading && !isError && (
            <span className="text-muted-foreground/50">
              API <span className="font-mono text-muted-foreground">
                :{new URL(serverState.backend_url).port}
              </span>
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
