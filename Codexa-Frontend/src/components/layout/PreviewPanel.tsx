import { useState, useEffect } from "react";
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
} from "lucide-react";

type DeviceMode = "desktop" | "tablet" | "mobile";

interface PreviewPanelProps {
  isOpen: boolean;
  onClose: () => void;
  previewUrl: string;
}

export function PreviewPanel({
  isOpen,
  onClose,
  previewUrl,
}: PreviewPanelProps) {

  const [deviceMode, setDeviceMode] = useState<DeviceMode>("desktop");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isPlaying, setIsPlaying] = useState(true);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (previewUrl) {
      setIsLoading(true);
    }
  }, [previewUrl]);

  const handleRefresh = () => {
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
  };

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
            Live
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
            onClick={() => setIsPlaying(!isPlaying)}
            className={cn(
              "p-2 rounded-lg transition-all duration-200",
              isPlaying
                ? "text-emerald-500 bg-emerald-500/10 hover:bg-emerald-500/20"
                : "text-muted-foreground hover:text-foreground hover:bg-secondary"
            )}
          >
            {isPlaying ? (
              <Pause className="w-4 h-4" />
            ) : (
              <Play className="w-4 h-4" />
            )}
          </button>

          <button
            onClick={handleRefresh}
            className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary transition-all duration-200"
          >
            <RefreshCw
              className={cn("w-4 h-4", isRefreshing && "animate-spin")}
            />
          </button>

          <button
            onClick={() => window.open(previewUrl, "_blank")}
            className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary transition-all duration-200"
          >
            <ExternalLink className="w-4 h-4" />
          </button>

        </div>

      </div>

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
                <span className="text-[11px] text-muted-foreground font-mono">
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

                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                      Installing dependencies
                    </div>

                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                      Building project
                    </div>

                    <div className="flex items-center gap-2">
                      <Loader2 className="w-3.5 h-3.5 animate-spin text-primary" />
                      Starting dev server
                    </div>

                    <div className="flex items-center gap-2">
                      <Loader2 className="w-3.5 h-3.5 animate-spin text-primary" />
                      Waiting for preview URL
                    </div>

                  </div>

                  <div className="mt-4 text-[11px] text-muted-foreground text-center">
                    CODEXA AI is preparing your project...
                  </div>

                </div>

              </div>
            )}

            <iframe
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

          <div className="flex items-center gap-2">
            <Loader2 className="w-3.5 h-3.5 text-primary animate-spin" />
            <span>Dev server running</span>
          </div>

        </div>

        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs text-muted-foreground">
            Updated just now
          </span>
        </div>

      </div>

    </div>
  );
}