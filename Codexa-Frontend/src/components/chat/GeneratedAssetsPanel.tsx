import { useEffect, useMemo, useState } from "react";
import {
  Download,
  ExternalLink,
  FileText,
  Image as ImageIcon,
  Minus,
  Plus,
} from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

export interface UmlDiagramAsset {
  diagram_type: string;
  url: string;
  file_path?: string;
}

interface GeneratedAssetsPanelProps {
  projectTitle?: string | null;
  umlDiagrams: UmlDiagramAsset[];
  pptUrl?: string | null;
  viewerUrl?: string | null;
  isGeneratingUml?: boolean;
  isGeneratingPpt?: boolean;
}

function prettyDiagramName(value: string) {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

export function GeneratedAssetsPanel({
  projectTitle,
  umlDiagrams,
  pptUrl,
  viewerUrl,
  isGeneratingUml = false,
  isGeneratingPpt = false,
}: GeneratedAssetsPanelProps) {
  const [selectedDiagram, setSelectedDiagram] = useState<UmlDiagramAsset | null>(
    null,
  );
  const [zoom, setZoom] = useState(1);
  const [showPptViewer, setShowPptViewer] = useState(true);

  useEffect(() => {
    setZoom(1);
  }, [selectedDiagram?.url]);
  console.log(viewerUrl);
  
  const hasContent =
    umlDiagrams.length > 0 || Boolean(pptUrl) || isGeneratingUml || isGeneratingPpt;
  const canEmbedViewer = useMemo(() => Boolean(viewerUrl), [viewerUrl]);

  if (!hasContent) return null;

  return (
    <>
      <div className="space-y-4 animate-fade-in-up">
        {(isGeneratingUml || isGeneratingPpt) && (
          <div
            className={cn(
              "rounded-3xl border border-white/10 bg-[#0f172acc] px-5 py-4 text-slate-100 backdrop-blur-xl",
              "shadow-lg shadow-black/20",
            )}
          >
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1">
                {[0, 1, 2].map((index) => (
                  <span
                    key={index}
                    className="h-2.5 w-2.5 rounded-full bg-sky-400 animate-bounce"
                    style={{ animationDelay: `${index * 140}ms` }}
                  />
                ))}
              </div>
              <div>
                <p className="text-sm font-semibold">
                  {isGeneratingPpt && isGeneratingUml
                    ? "Preparing presentation and UML assets"
                    : isGeneratingPpt
                      ? "Preparing presentation assets"
                      : "Preparing UML diagrams"}
                </p>
                <p className="text-xs text-slate-400">
                  CODEXA is generating reusable files for this project.
                </p>
              </div>
            </div>
          </div>
        )}

        {umlDiagrams.length > 0 && (
          <section
            className={cn(
              "rounded-3xl border border-white/10 bg-[#0b1220]/92 p-5 text-slate-100 backdrop-blur-xl",
              "shadow-lg shadow-black/20",
            )}
          >
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-sky-300">
                  UML Gallery
                </p>
                <h3 className="text-lg font-semibold text-white">
                  Reusable system diagrams
                </h3>
                <p className="text-sm text-slate-400">
                  Click any diagram to inspect it full-screen, zoom in, or
                  download it.
                </p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-right">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-400">
                  Project
                </p>
                <p className="text-sm font-medium text-white">
                  {projectTitle || "Current project"}
                </p>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {umlDiagrams.map((diagram) => (
                <div
                  key={diagram.diagram_type}
                  className={cn(
                    "group overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03]",
                    "transition-all duration-300 hover:-translate-y-0.5 hover:border-sky-300/40 hover:shadow-lg hover:shadow-sky-500/10",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => setSelectedDiagram(diagram)}
                    className="block w-full text-left"
                  >
                    <div className="aspect-[16/10] overflow-hidden bg-slate-950/80">
                      <img
                        src={diagram.url}
                        alt={prettyDiagramName(diagram.diagram_type)}
                        loading="lazy"
                        className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.02]"
                      />
                    </div>
                  </button>
                  <div className="flex items-center justify-between gap-3 px-4 py-3">
                    <button
                      type="button"
                      onClick={() => setSelectedDiagram(diagram)}
                      className="min-w-0 text-left"
                    >
                      <p className="truncate text-sm font-semibold text-white">
                        {prettyDiagramName(diagram.diagram_type)}
                      </p>
                      <p className="text-xs text-slate-400">
                        Click to open full-screen
                      </p>
                    </button>
                    <a
                      href={diagram.url}
                      download
                      target="_blank"
                      rel="noreferrer"
                      onClick={(event) => event.stopPropagation()}
                      className={cn(
                        "inline-flex h-9 w-9 items-center justify-center rounded-full border border-white/10 bg-white/5",
                        "text-slate-200 transition hover:border-sky-300/40 hover:bg-sky-400/10 hover:text-white",
                      )}
                      aria-label={`Download ${prettyDiagramName(diagram.diagram_type)}`}
                    >
                      <Download className="h-4 w-4" />
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {(pptUrl || isGeneratingPpt) && (
          <section
            className={cn(
              "rounded-3xl border border-white/10 bg-[#0b1220]/92 p-5 text-slate-100 backdrop-blur-xl",
              "shadow-lg shadow-black/20",
            )}
          >
            <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-sky-300">
                  Presentation
                </p>
                <h3 className="text-lg font-semibold text-white">
                  Downloadable project deck
                </h3>
                <p className="text-sm text-slate-400">
                  View the generated presentation inline when a public URL is
                  available, or download the `.pptx` directly.
                </p>
              </div>

              {pptUrl && (
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setShowPptViewer((value) => !value)}
                    className={cn(
                      "inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition",
                      "border-white/10 bg-white/5 text-slate-100 hover:border-sky-300/35 hover:bg-sky-400/10",
                    )}
                  >
                    <ExternalLink className="h-4 w-4" />
                    {showPptViewer ? "Hide PPT" : "View PPT"}
                  </button>
                  <a
                    href={pptUrl}
                    download
                    target="_blank"
                    rel="noreferrer"
                    className={cn(
                      "inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition",
                      "border-white/10 bg-white/5 text-slate-100 hover:border-sky-300/35 hover:bg-sky-400/10",
                    )}
                  >
                    <Download className="h-4 w-4" />
                    Download PPT
                  </a>
                </div>
              )}
            </div>

            {pptUrl ? (
              showPptViewer ? (
                canEmbedViewer ? (
                  <div className="overflow-hidden rounded-2xl border border-white/10 bg-slate-950/80">
                    <iframe
                      title="Generated PPT Preview"
                      src={viewerUrl ?? undefined}
                      className="h-[520px] w-full border-0"
                    />
                  </div>
                ) : (
                  <div className="rounded-2xl border border-dashed border-white/15 bg-white/[0.03] px-5 py-6">
                    <div className="flex items-start gap-3">
                      <div className="rounded-2xl border border-white/10 bg-white/5 p-3">
                        <FileText className="h-5 w-5 text-sky-300" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-white">
                          Inline viewer needs a public PPT URL
                        </p>
                        <p className="mt-1 text-sm text-slate-400">
                          The presentation file is ready to download. The Google
                          Docs embed will appear automatically when the backend
                          is reachable from a public host.
                        </p>
                      </div>
                    </div>
                  </div>
                )
              ) : null
            ) : (
              <div className="rounded-2xl border border-dashed border-white/15 bg-white/[0.03] px-5 py-6">
                <p className="text-sm text-slate-400">
                  Preparing the project deck…
                </p>
              </div>
            )}
          </section>
        )}
      </div>

      <Dialog
        open={Boolean(selectedDiagram)}
        onOpenChange={(open) => {
          if (!open) setSelectedDiagram(null);
        }}
      >
        <DialogContent className="max-w-6xl border-white/10 bg-[#08101d]/96 p-0 text-slate-100">
          <DialogHeader className="border-b border-white/10 px-6 py-4">
            <DialogTitle className="text-white">
              {prettyDiagramName(selectedDiagram?.diagram_type || "Diagram")}
            </DialogTitle>
          </DialogHeader>

          <div className="flex items-center justify-between gap-3 border-b border-white/10 px-6 py-3">
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <ImageIcon className="h-4 w-4 text-sky-300" />
              Inspect and download the generated diagram.
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setZoom((value) => Math.max(0.7, value - 0.15))}
                className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-white/10 bg-white/5 transition hover:border-sky-300/35 hover:bg-sky-400/10"
                aria-label="Zoom out"
              >
                <Minus className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => setZoom((value) => Math.min(2.4, value + 0.15))}
                className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-white/10 bg-white/5 transition hover:border-sky-300/35 hover:bg-sky-400/10"
                aria-label="Zoom in"
              >
                <Plus className="h-4 w-4" />
              </button>
              {selectedDiagram && (
                <a
                  href={selectedDiagram.url}
                  download
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium transition hover:border-sky-300/35 hover:bg-sky-400/10"
                >
                  <Download className="h-4 w-4" />
                  Download
                </a>
              )}
            </div>
          </div>

          <div className="max-h-[78vh] overflow-auto bg-[#050b14] p-6">
            <div className="flex min-h-[62vh] items-center justify-center rounded-3xl border border-white/10 bg-slate-950/80 p-6">
              {selectedDiagram && (
                <img
                  src={selectedDiagram.url}
                  alt={prettyDiagramName(selectedDiagram.diagram_type)}
                  className="max-h-[68vh] w-auto origin-center transition-transform duration-200"
                  style={{ transform: `scale(${zoom})` }}
                />
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
