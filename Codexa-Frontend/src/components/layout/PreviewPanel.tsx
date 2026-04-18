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
  Play,
  Pause,
  Terminal,
  AlertCircle,
} from "lucide-react";

type DeviceMode = "desktop" | "tablet" | "mobile";

interface ProgressStep {
  id: string;
  label: string;
  done: boolean;
}

interface PreviewPanelProps {
  isOpen: boolean;
  onClose: () => void;
  previewUrl: string;
  projectId?: string;
}

const DEFAULT_PROGRESS: ProgressStep[] = [
  { id: "copying", label: "Copying files", done: false },
  { id: "installing", label: "Installing dependencies", done: false },
  { id: "starting", label: "Starting servers", done: false },
  { id: "ready", label: "Project running", done: false },
];

export function PreviewPanel({
  isOpen,
  onClose,
  previewUrl,
  projectId,
}: PreviewPanelProps) {
  const [deviceMode, setDeviceMode] = useState<DeviceMode>("desktop");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isPlaying, setIsPlaying] = useState(true);
  const [isLoading, setIsLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [showTerminal, setShowTerminal] = useState(false);
  const [progressSteps, setProgressSteps] = useState<ProgressStep[]>(DEFAULT_PROGRESS);
  
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  // Check preview status via polling when projectId changes and no previewUrl yet
  useEffect(() => {
    if (!isOpen || !projectId || previewUrl) {
      return;
    }

    // Start polling for preview status
    const checkStatus = async () => {
      try {
        const res = await fetch("http://localhost:8000/preview/status");
        const data = await res.json();
        
        if (data.status === "running") {
          // Update progress as we detect server is running
          setProgressSteps(DEFAULT_PROGRESS.map(s => ({ ...s, done: true })));
          setIsLoading(false);
          setLastUpdated(new Date());
          
          // Try to get the frontend URL
          if (pollingRef.current) {
            clearInterval(pollingRef.current);
          }
        }
      } catch (e) {
        // Ignore errors during polling
      }
    };

    // Update step status based on time passed
    let stepIndex = 0;
    const stepTimer = setInterval(() => {
      if (stepIndex < 3) {
        setProgressSteps(prev => {
          const updated = [...prev];
          updated[stepIndex] = { ...updated[stepIndex], done: true };
          return updated;
        });
        stepIndex++;
      }
    }, 2000); // Each step takes ~2 seconds

    // Start polling
    checkStatus();
    pollingRef.current = setInterval(checkStatus, 3000);

    return () => {
      if (stepTimer) clearInterval(stepTimer);
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, [isOpen, projectId, previewUrl]);

  // Reset progress when previewUrl changes
  useEffect(() => {
    if (previewUrl) {
      setIsLoading(false);
      setLastUpdated(new Date());
      setProgressSteps(DEFAULT_PROGRESS.map(s => ({ ...s, done: true })));
    } else {
      setProgressSteps(DEFAULT_PROGRESS);
    }
  }, [previewUrl]);

  // Handle refresh
  const handleRefresh = useCallback(() => {
    if (!previewUrl || isRefreshing) return;

    setIsRefreshing(true);

    setTimeout(() => {
      const iframe = document.getElementById(
        "codexa-preview-iframe"
      ) as HTMLIFrameElement | null;

      if (iframe) {
        iframe.src = previewUrl;
        setIsLoading(true);
      }

      setIsRefreshing(false);
    }, 400);
  }, [previewUrl, isRefreshing]);

  // Handle play/pause
  const handlePlayPause = useCallback(() => {
    setIsPlaying((prev) => !prev);
  }, []);

  // Handle external open
  const handleOpenExternal = useCallback(() => {
    if (previewUrl) {
      window.open(previewUrl, "_blank");
    }
  }, [previewUrl]);

  // Format last updated time
  const formatLastUpdated = useCallback(() => {
    if (!lastUpdated) return "Never";
    const now = new Date();
    const diff = Math.floor((now.getTime() - lastUpdated.getTime()) / 1000);
    if (diff < 5) return "Just now";
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return lastUpdated.toLocaleTimeString();
  }, [lastUpdated]);

  if (!isOpen) return null;

  return (
    <div className="h-full flex flex-col bg-card/50 backdrop-blur-sm border-l border-border/50 relative overflow-hidden">
      {/* Ambient background */}
      <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-accent/5 pointer-events-none" />

      {/* Header */}
      <div className="px-4 py-3 border-b border-border/50 flex items-center justify-between shrink-0 bg-secondary/30 backdrop-blur-sm relative z-10">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-sm font-semibold text-foreground">
              Preview
            </span>
          </div>

          <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 font-medium">
            {previewUrl ? "Live" : "Idle"}
          </span>
        </div>

        <button
          onClick={onClose}
          className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary transition-all duration-200"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Device Controls */}
      <div className="px-4 py-2 border-b border-border/50 flex items-center justify-between bg-background/30 relative z-10">
        <div className="flex items-center gap-1 p-1 rounded-xl bg-secondary/50 border border-border/50">
          {[
            { mode: "desktop" as DeviceMode, icon: Monitor },
            { mode: "tablet" as DeviceMode, icon: Tablet },
            { mode: "mobile" as DeviceMode, icon: Smartphone },
          ].map(({ mode, icon: Icon }) => (
            <button
              key={mode}
              onClick={() => setDeviceMode(mode)}
              className={cn(
                "p-2 rounded-lg transition-all duration-200",
                deviceMode === mode
                  ? "bg-primary text-primary-foreground shadow-lg shadow-primary/30"
                  : "text-muted-foreground hover:text-foreground hover:bg-secondary/80"
              )}
            >
              <Icon className="w-4 h-4" />
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={handlePlayPause}
            className={cn(
              "p-2 rounded-lg transition-all duration-200",
              isPlaying
                ? "text-emerald-500 bg-emerald-500/10 hover:bg-emerald-500/20"
                : "text-muted-foreground hover:text-foreground hover:bg-secondary"
            )}
            title={isPlaying ? "Pause auto-refresh" : "Resume"}
          >
            {isPlaying ? (
              <Pause className="w-4 h-4" />
            ) : (
              <Play className="w-4 h-4" />
            )}
          </button>

          <button
            onClick={handleRefresh}
            disabled={!previewUrl || isRefreshing}
            className={cn(
              "p-2 rounded-lg transition-all duration-200",
              !previewUrl || isRefreshing
                ? "text-muted-foreground/50"
                : "text-muted-foreground hover:text-foreground hover:bg-secondary",
              isRefreshing && "animate-spin"
            )}
            title="Refresh preview"
          >
            <RefreshCw className="w-4 h-4" />
          </button>

          <button
            onClick={() => setShowTerminal(!showTerminal)}
            className={cn(
              "p-2 rounded-lg transition-all duration-200",
              showTerminal
                ? "text-primary bg-primary/10"
                : "text-muted-foreground hover:text-foreground hover:bg-secondary"
            )}
            title="Show build logs"
          >
            <Terminal className="w-4 h-4" />
          </button>

          <button
            onClick={handleOpenExternal}
            disabled={!previewUrl}
            className={cn(
              "p-2 rounded-lg transition-all duration-200",
              !previewUrl
                ? "text-muted-foreground/50"
                : "text-muted-foreground hover:text-foreground hover:bg-secondary"
            )}
            title="Open in new tab"
          >
            <ExternalLink className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Terminal/Build Logs Panel */}
      {showTerminal && isLoading && (
        <div className="border-b border-border/50 max-h-48 overflow-auto bg-[#0d1117] p-3 relative z-10">
          <div className="text-xs font-mono space-y-1">
            {progressSteps.map((step) => (
              <div
                key={step.id}
                className={cn(
                  "flex items-center gap-2",
                  step.done ? "text-emerald-400" : "text-yellow-400"
                )}
              >
                {step.done ? (
                  <CheckCircle2 className="w-3.5 h-3.5" />
                ) : (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                )}
                <span>{step.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Preview Content */}
      <div className="flex-1 overflow-hidden p-4 relative z-10 dot-pattern">
        <div
          className={cn(
            "h-full mx-auto bg-background rounded-xl border border-border shadow-2xl overflow-hidden transition-all duration-500",
            deviceMode === "desktop" && "w-full",
            deviceMode === "tablet" && "max-w-[768px]",
            deviceMode === "mobile" && "max-w-[375px]"
          )}
        >
          {/* Browser Chrome */}
          <div className="h-9 bg-secondary/50 border-b border-border/50 flex items-center px-3 gap-2">
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-full bg-red-500/80" />
              <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
              <div className="w-3 h-3 rounded-full bg-green-500/80" />
            </div>

            <div className="flex-1 mx-4">
              <div className="h-6 bg-background/80 rounded-lg flex items-center px-3 border border-border/50">
                <span className="text-[11px] text-muted-foreground font-mono truncate">
                  {previewUrl || "localhost"}
                </span>
              </div>
            </div>
          </div>

          {/* Preview + Loader */}
          <div className="relative w-full h-[calc(100%-2.25rem)]">
            {isLoading && (
              <div className="absolute inset-0 flex items-center justify-center bg-background/90 backdrop-blur-sm z-20">
                <div className="w-[260px] rounded-xl border border-border bg-card shadow-xl p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Loader2 className="w-4 h-4 animate-spin text-primary" />
                    <span className="text-sm font-medium">Preparing Preview</span>
                  </div>

                  <div className="space-y-2 text-xs text-muted-foreground font-mono">
                    {progressSteps.map((step) => (
                      <div
                        key={step.id}
                        className={cn(
                          "flex items-center gap-2",
                          step.done && "text-emerald-500"
                        )}
                      >
                        {step.done ? (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                        ) : (
                          <Loader2 className="w-3.5 h-3.5 animate-spin text-primary" />
                        )}
                        {step.label}
                      </div>
                    ))}
                  </div>

                  <div className="mt-4 text-[11px] text-muted-foreground text-center">
                    CODEXA AI is preparing your project...
                  </div>
                </div>
              </div>
            )}

            <iframe
              ref={iframeRef}
              id="codexa-preview-iframe"
              src={previewUrl}
              sandbox="allow-scripts allow-same-origin"
              className="w-full h-full border-none bg-white"
              onLoad={() => setIsLoading(false)}
            />
          </div>
        </div>
      </div>

      {/* Status Bar */}
      <div className="px-4 py-2.5 border-t border-border/50 bg-secondary/30 backdrop-blur-sm flex items-center justify-between relative z-10">
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
            <span>Build passed</span>
          </div>

          {previewUrl && (
            <div className="flex items-center gap-2">
              <Loader2 className="w-3.5 h-3.5 text-primary animate-spin" />
              <span>Dev server running</span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs text-muted-foreground">
            Updated {formatLastUpdated()}
          </span>
        </div>
      </div>
    </div>
  );
}