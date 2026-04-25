import { useEffect, useMemo, useState } from "react";
import { Highlight, themes } from "prism-react-renderer";
import { Check, Copy, Eye, Play, RotateCcw, Terminal } from "lucide-react";

import { cn } from "@/lib/utils";

interface CodeBlockProps {
  code: string;
  language?: string;
  onPreview?: () => void;
  previewLabel?: string;
  livePreviewHtml?: string;
  livePreviewLabel?: string;
}

function normalizeLanguage(language?: string) {
  const value = (language || "text").trim().toLowerCase();
  if (value === "js") return "javascript";
  if (value === "ts") return "typescript";
  if (value === "sh") return "bash";
  if (value === "html") return "markup";
  return value || "text";
}

export function CodeBlock({
  code,
  language = "typescript",
  onPreview,
  previewLabel = "Preview",
  livePreviewHtml,
  livePreviewLabel = "Live",
}: CodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const [activeView, setActiveView] = useState<"code" | "live">("code");
  const [liveFrameKey, setLiveFrameKey] = useState(0);
  const prismLanguage = useMemo(
    () => normalizeLanguage(language),
    [language],
  );
  const displayCode = useMemo(() => code.replace(/\s+$/, ""), [code]);
  const hasLivePreview = Boolean(livePreviewHtml?.trim());

  useEffect(() => {
    if (!hasLivePreview && activeView === "live") {
      setActiveView("code");
    }
  }, [activeView, hasLivePreview]);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  const handleShowLivePreview = () => {
    if (!hasLivePreview) return;
    if (activeView !== "live") {
      setLiveFrameKey((prev) => prev + 1);
    }
    setActiveView("live");
  };

  const handleShowCode = () => {
    setActiveView("code");
  };

  const handleReloadLivePreview = () => {
    setLiveFrameKey((prev) => prev + 1);
  };

  return (
    <div className="my-3 overflow-hidden rounded-[22px] border border-white/12 bg-[linear-gradient(180deg,rgba(16,24,44,0.76),rgba(8,16,29,0.9))] backdrop-blur-xl shadow-[0_20px_70px_rgba(0,0,0,0.25)]">
      <style>{`
        @keyframes codeblock-ring-ping {
          0% { transform: scale(1); opacity: 0.55; }
          70% { transform: scale(1.8); opacity: 0; }
          100% { transform: scale(1.8); opacity: 0; }
        }
        @keyframes codeblock-breath {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.45; transform: scale(0.8); }
        }
      `}</style>

      <div className="border-b border-white/10 bg-[linear-gradient(90deg,rgba(16,24,44,0.72),rgba(20,30,58,0.62),rgba(13,24,48,0.72))] backdrop-blur-md px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <div className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/12 ring-1 ring-primary/20 shadow-lg shadow-primary/10">
              <span className="absolute inset-0 rounded-xl bg-primary/10 opacity-60" />
              <span
                className="absolute inset-0 rounded-xl ring-1 ring-primary/20"
                style={{ animation: "codeblock-ring-ping 1.8s ease-out infinite" }}
              />
              <Terminal className="relative z-10 h-4 w-4 text-primary" />
            </div>

            <div className="min-w-0">
              <p className="truncate text-[11px] font-semibold uppercase tracking-[0.22em] text-primary/85">
                Code Workspace
              </p>
              <div className="mt-1 flex items-center gap-2 text-[11px] text-slate-300">
                <span className="truncate font-medium">{language || "text"}</span>
                <span className="h-1 w-1 rounded-full bg-primary/70" />
                <span className="truncate text-slate-400">
                  {activeView === "live" ? "Live rendering active" : "Source view"}
                </span>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {hasLivePreview && (
              <div className="flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.06] p-1 shadow-inner shadow-black/20 backdrop-blur-md">
                <button
                  type="button"
                  onClick={handleShowCode}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition",
                    activeView === "code"
                      ? "bg-primary/15 text-primary ring-1 ring-primary/25"
                      : "text-slate-300 hover:bg-white/5",
                  )}
                >
                  <Terminal className="h-3.5 w-3.5" />
                  Code
                </button>
                <button
                  type="button"
                  onClick={handleShowLivePreview}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition",
                    activeView === "live"
                      ? "bg-emerald-500/15 text-emerald-200 ring-1 ring-emerald-400/30"
                      : "text-emerald-300 hover:bg-emerald-500/10",
                  )}
                >
                  <Eye className="h-3.5 w-3.5" />
                  {livePreviewLabel}
                </button>
              </div>
            )}

            {onPreview && !hasLivePreview && (
              <button
                type="button"
                onClick={onPreview}
                className="inline-flex items-center gap-1.5 rounded-full border border-primary/25 bg-primary/12 px-3 py-1.5 text-xs font-medium text-primary backdrop-blur-sm transition hover:bg-primary/18"
              >
                <Play className="h-3.5 w-3.5" />
                {previewLabel}
              </button>
            )}

            {hasLivePreview && activeView === "live" && (
              <button
                type="button"
                onClick={handleReloadLivePreview}
                className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-slate-200 backdrop-blur-sm transition hover:bg-white/10"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Reload
              </button>
            )}

            <button
              type="button"
              onClick={handleCopy}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition",
                copied
                  ? "border-emerald-500/30 bg-emerald-500/12 text-emerald-300"
                  : "border-white/10 bg-white/5 text-slate-200 backdrop-blur-sm hover:bg-white/10",
              )}
            >
              {copied ? (
                <Check className="h-3.5 w-3.5" />
              ) : (
                <Copy className="h-3.5 w-3.5" />
              )}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        </div>
      </div>

      {activeView === "code" ? (
        <div className="max-h-[820px] overflow-auto px-0 py-0">
          <Highlight
            theme={themes.vsDark}
            code={displayCode}
            language={prismLanguage as never}
          >
            {({ className, style, tokens, getLineProps, getTokenProps }) => (
              <pre
                className={cn(
                  className,
                  "m-0 min-w-full bg-transparent px-0 py-3 text-[13px] leading-6",
                )}
                style={{ ...style, background: "transparent" }}
              >
                {tokens.map((line, index) => (
                  <div
                    key={index}
                    {...getLineProps({ line })}
                    className="table w-full table-fixed"
                  >
                    <span className="table-cell w-12 select-none pl-4 pr-3 text-right text-[11px] text-slate-500">
                      {index + 1}
                    </span>
                    <span className="table-cell pr-5">
                      {line.length === 0 ? (
                        <span>{" "}</span>
                      ) : (
                        line.map((token, tokenIndex) => (
                          <span
                            key={tokenIndex}
                            {...getTokenProps({ token })}
                          />
                        ))
                      )}
                    </span>
                  </div>
                ))}
              </pre>
            )}
          </Highlight>
        </div>
      ) : (
        <div className="bg-[linear-gradient(180deg,rgba(8,16,29,0.78),rgba(8,16,29,0.94))] backdrop-blur-md p-4">
          <div className="mb-3 flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/[0.05] px-4 py-3 backdrop-blur-md">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-300/90">
                Live Preview
              </p>
              <p className="text-xs text-slate-400">
                Interactive rendering of the generated small project
              </p>
            </div>
            <div className="flex items-center gap-[3px]">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="h-1.5 w-1.5 rounded-full bg-emerald-400"
                  style={{
                    animation: `codeblock-breath 1.2s ease-in-out ${i * 0.2}s infinite`,
                  }}
                />
              ))}
            </div>
          </div>

          <div className="overflow-hidden rounded-2xl border border-white/10 bg-white shadow-lg shadow-black/20">
            <iframe
              key={liveFrameKey}
              title="Live small project preview"
              srcDoc={livePreviewHtml}
              sandbox="allow-scripts allow-forms allow-modals allow-popups allow-downloads"
              className="h-[560px] w-full bg-white"
            />
          </div>
        </div>
      )}
    </div>
  );
}
