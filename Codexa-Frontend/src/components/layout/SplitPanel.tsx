import { useMemo, useState, useRef, useEffect } from "react";
import { cn, isElementNearBottom } from "@/lib/utils";
import {
  Smartphone,
  Monitor,
  Tablet,
  RefreshCw,
  ExternalLink,
  X,
  Sparkles,
  CheckCircle2,
  Copy,
  Check,
  FileCode,
  Download,
  Loader2,
  ChevronDown,
} from "lucide-react";
import { toast } from "sonner";
import { Highlight, themes } from "prism-react-renderer";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";
import { useAppData } from "@/context/useAppData";

const splitCodeJumpButtonClass = cn(
  "absolute z-20 right-3 bottom-3",
  "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium",
  "bg-[hsl(var(--chat-surface)/0.95)] border border-[hsl(var(--chat-surface-border)/0.9)]",
  "shadow-md shadow-black/10 text-foreground",
  "hover:bg-muted/90 transition-colors",
);

type DeviceMode = "desktop" | "tablet" | "mobile";

interface SplitPanelProps {
  isOpen: boolean;
  onClose: () => void;
  previewUrl: string;
}

export function SplitPanel({ isOpen, onClose, previewUrl }: SplitPanelProps) {
  const { selectedFile } = useAppData();
  const [deviceMode, setDeviceMode] = useState<DeviceMode>("desktop");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [copied, setCopied] = useState(false);
  const [isPreviewLoading, setIsPreviewLoading] = useState(true);

  const activeCode = useMemo(() => {
    if (!selectedFile?.content) return "";
    return selectedFile.content;
  }, [selectedFile]);

  const activeLanguage = useMemo(() => {
    if (!selectedFile?.language) return "tsx";
    return selectedFile.language;
  }, [selectedFile]);

  const splitCodeScrollRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const [showJumpToBottom, setShowJumpToBottom] = useState(false);

  const scrollSplitCodeToBottom = (behavior: ScrollBehavior = "smooth") => {
    const el = splitCodeScrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior });
  };

  const handleSplitCodeScroll = () => {
    const el = splitCodeScrollRef.current;
    if (!el) return;
    const near = isElementNearBottom(el);
    stickToBottomRef.current = near;
    const hasOverflow = el.scrollHeight > el.clientHeight + 4;
    const jump = !near && hasOverflow;
    setShowJumpToBottom((p) => (p === jump ? p : jump));
  };

  useEffect(() => {
    stickToBottomRef.current = true;
    setShowJumpToBottom(false);
    requestAnimationFrame(() => {
      const el = splitCodeScrollRef.current;
      if (!el) return;
      el.scrollTo({ top: el.scrollHeight, behavior: "auto" });
    });
  }, [selectedFile?._id]);

  useEffect(() => {
    requestAnimationFrame(() => {
      const el = splitCodeScrollRef.current;
      if (!el) return;
      if (stickToBottomRef.current) {
        el.scrollTo({ top: el.scrollHeight, behavior: "auto" });
      }
    });
  }, [activeCode, selectedFile?._id]);

  const handleRefresh = () => {
    setIsRefreshing(true);
    setTimeout(() => {
      const iframe = document.getElementById("codexa-split-iframe") as HTMLIFrameElement | null;
      if (iframe && previewUrl) {
        iframe.src = previewUrl;
        setIsPreviewLoading(true);
      }
      setIsRefreshing(false);
    }, 400);
  };

  const handleCopy = () => {
    if (!activeCode) return;
    navigator.clipboard.writeText(activeCode);
    setCopied(true);
    toast.success("Code copied!");
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    if (!activeCode || !selectedFile?.name) return;
    const blob = new Blob([activeCode], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = selectedFile.name;
    a.click();
    URL.revokeObjectURL(url);
    toast.success(`Downloaded ${selectedFile.name}`);
  };

  if (!isOpen) return null;

  return (
    <div className="h-full flex flex-col bg-card border-l border-border">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border flex items-center justify-between shrink-0 bg-secondary/30">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-accent" />
            <span className="text-sm font-semibold text-foreground">Split View</span>
          </div>
          <span className="text-xs px-2 py-0.5 rounded-full bg-accent/10 text-accent border border-accent/20">
            Preview + Code
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary transition-all duration-200"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Split Content */}
      <ResizablePanelGroup direction="vertical" className="flex-1">
        {/* Preview Section */}
        <ResizablePanel defaultSize={50} minSize={25}>
          <div className="h-full flex flex-col">
            {/* Preview Controls */}
            <div className="px-3 py-2 border-b border-border flex items-center justify-between bg-background/50">
              <div className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                <span className="text-xs font-medium text-muted-foreground">Preview</span>
              </div>
              <div className="flex items-center gap-1">
                <div className="flex items-center gap-0.5 p-0.5 rounded-md bg-secondary/50">
                  {[
                    { mode: "desktop" as DeviceMode, icon: Monitor },
                    { mode: "tablet" as DeviceMode, icon: Tablet },
                    { mode: "mobile" as DeviceMode, icon: Smartphone },
                  ].map(({ mode, icon: Icon }) => (
                    <button
                      key={mode}
                      onClick={() => setDeviceMode(mode)}
                      className={cn(
                        "p-1.5 rounded transition-all duration-200",
                        deviceMode === mode
                          ? "bg-background text-foreground shadow-sm"
                          : "text-muted-foreground hover:text-foreground"
                      )}
                    >
                      <Icon className="w-3.5 h-3.5" />
                    </button>
                  ))}
                </div>
                <button
                  onClick={handleRefresh}
                  className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary transition-all"
                >
                  <RefreshCw className={cn("w-3.5 h-3.5", isRefreshing && "animate-spin")} />
                </button>
                <button className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary transition-all">
                  <ExternalLink className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {/* Preview Content */}
            <div className="flex-1 overflow-hidden p-3 bg-[repeating-linear-gradient(45deg,hsl(var(--secondary)/0.2)_0px,hsl(var(--secondary)/0.2)_1px,transparent_1px,transparent_8px)]">
              <div className={cn(
                "h-full mx-auto bg-background rounded-lg border border-border shadow-lg overflow-hidden transition-all duration-300",
                deviceMode === "desktop" && "w-full",
                deviceMode === "tablet" && "max-w-[400px]",
                deviceMode === "mobile" && "max-w-[280px]"
              )}>
                {/* Mini Browser Chrome */}
                <div className="h-6 bg-secondary/50 border-b border-border flex items-center px-2 gap-1.5">
                  <div className="flex items-center gap-1">
                    <div className="w-2 h-2 rounded-full bg-red-500/70" />
                    <div className="w-2 h-2 rounded-full bg-yellow-500/70" />
                    <div className="w-2 h-2 rounded-full bg-green-500/70" />
                  </div>
                  <div className="flex-1 mx-2">
                    <div className="h-3.5 bg-background/60 rounded text-[8px] flex items-center px-2 text-muted-foreground">
                      localhost:3000
                    </div>
                  </div>
                </div>

                {/* Preview Area */}
                <div className="h-[calc(100%-1.5rem)] relative">
                  {(!previewUrl || isPreviewLoading) && (
                    <div className="absolute inset-0 z-10 flex items-center justify-center bg-background/90 backdrop-blur-sm p-4">
                      <div className="w-full max-w-[240px] rounded-xl border border-border bg-card p-4 shadow-xl">
                        <div className="flex items-center gap-2 mb-3">
                          <Loader2 className="w-4 h-4 animate-spin text-primary" />
                          <span className="text-sm font-medium">
                            {previewUrl ? "Loading Preview" : "Preparing Preview"}
                          </span>
                        </div>
                        <div className="space-y-2">
                          <div className="h-2 rounded bg-muted animate-pulse" />
                          <div className="h-2 rounded bg-muted/80 animate-pulse" />
                          <div className="h-2 rounded bg-muted/60 animate-pulse" />
                        </div>
                        <p className="text-[11px] text-muted-foreground mt-3">
                          {previewUrl
                            ? "Connecting to dev server..."
                            : "Waiting for preview URL from backend..."}
                        </p>
                      </div>
                    </div>
                  )}

                  {previewUrl ? (
                    <iframe
                      id="codexa-split-iframe"
                      src={previewUrl}
                      sandbox="allow-scripts allow-same-origin"
                      className="w-full h-full border-none bg-white"
                      onLoad={() => setIsPreviewLoading(false)}
                    />
                  ) : (
                    <div className="h-full flex flex-col items-center justify-center gap-2 p-4">
                      <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-md animate-float">
                        <Sparkles className="w-5 h-5 text-white" />
                      </div>
                      <div className="text-center">
                        <h3 className="text-sm font-semibold text-foreground">Preview Not Ready</h3>
                        <p className="text-[10px] text-muted-foreground">Generate or open a project first</p>
                      </div>
                    </div>
                  )}

                  <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex items-center gap-1.5 px-2 py-1 rounded-full bg-emerald-500/10">
                    <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                    <span className="text-[10px] font-medium text-emerald-500">
                      {previewUrl ? "Live" : "Idle"}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle className="bg-border/50 hover:bg-primary/30 transition-colors data-[panel-group-direction=vertical]:h-2" />

        {/* Code Section */}
        <ResizablePanel defaultSize={50} minSize={25}>
          <div className="relative h-full flex flex-col">
            {/* Code Controls */}
            <div className="px-3 py-2 border-b border-border flex items-center justify-between bg-background/50">
              <div className="flex items-center gap-2">
                <FileCode className="w-3.5 h-3.5 text-primary" />
                <span className="text-xs font-medium text-muted-foreground">
                  {selectedFile?.name || "No file selected"}
                </span>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={handleCopy}
                  disabled={!activeCode}
                  className={cn(
                    "flex items-center gap-1 px-2 py-1 rounded-md text-[10px] transition-all",
                    !activeCode && "opacity-50 cursor-not-allowed",
                    copied
                      ? "bg-emerald-500/10 text-emerald-500"
                      : "text-muted-foreground hover:text-foreground hover:bg-secondary"
                  )}
                >
                  {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                  <span>{copied ? "Copied" : "Copy"}</span>
                </button>
                <button
                  onClick={handleDownload}
                  disabled={!activeCode}
                  className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary transition-all"
                >
                  <Download className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {/* Code Content */}
            <div
              ref={splitCodeScrollRef}
              onScroll={handleSplitCodeScroll}
              className="flex-1 overflow-auto scrollbar-thin bg-[#011627] relative"
            >
              {activeCode ? (
                <Highlight theme={themes.nightOwl} code={activeCode} language={activeLanguage}>
                  {({ tokens, getLineProps, getTokenProps }) => (
                    <pre className="text-[11px] leading-relaxed p-3 min-h-full">
                      {tokens.map((line, i) => (
                        <div key={i} {...getLineProps({ line })} className="table-row hover:bg-white/5">
                          <span className="table-cell pr-4 text-slate-600 select-none text-right w-8">
                            {i + 1}
                          </span>
                          <span className="table-cell">
                            {line.map((token, key) => (
                              <span key={key} {...getTokenProps({ token })} />
                            ))}
                          </span>
                        </div>
                      ))}
                    </pre>
                  )}
                </Highlight>
              ) : (
                <div className="h-full p-3 space-y-3">
                  <div className="h-4 w-40 rounded bg-slate-700/60 animate-pulse" />
                  {Array.from({ length: 12 }).map((_, i) => (
                    <div key={i} className="flex items-center gap-3">
                      <div className="h-3 w-8 rounded bg-slate-700/50 animate-pulse" />
                      <div
                        className="h-3 rounded bg-slate-700/50 animate-pulse"
                        style={{ width: `${58 + ((i * 11) % 30)}%` }}
                      />
                    </div>
                  ))}
                  <p className="text-[11px] text-slate-400 pt-2">
                    Select a file from the project to view code.
                  </p>
                </div>
              )}
            </div>

            {showJumpToBottom && (
              <button
                type="button"
                onClick={() => {
                  stickToBottomRef.current = true;
                  setShowJumpToBottom(false);
                  scrollSplitCodeToBottom("smooth");
                }}
                className={splitCodeJumpButtonClass}
              >
                <ChevronDown className="w-3.5 h-3.5 opacity-80" />
                Latest
              </button>
            )}
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
