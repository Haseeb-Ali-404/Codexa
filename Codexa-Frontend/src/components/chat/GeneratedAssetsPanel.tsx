import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
  type WheelEvent as ReactWheelEvent,
} from "react";
import {
  CheckCircle2,
  Download,
  ExternalLink,
  FileText,
  Image as ImageIcon,
  Minus,
  Plus,
  Presentation,
  Sparkles,
} from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export interface UmlDiagramAsset {
  diagram_type: string;
  url: string;
  file_path?: string;
}

export interface GeneratedAssetsPanelProps {
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

function clampZoom(value: number) {
  return Math.min(3.2, Math.max(0.7, value));
}

const UML_ZOOM_STEP = 0.05;
const UML_DRAG_DAMPING = 0.68;

function PanelFrame({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-[24px] border border-white/10 bg-[linear-gradient(180deg,rgba(15,23,42,0.88),rgba(15,23,42,0.62))] shadow-[0_18px_48px_rgba(2,6,23,0.24)] backdrop-blur-xl">
      <div className="border-b border-white/8 bg-[radial-gradient(circle_at_top_right,rgba(99,102,241,0.16),transparent_34%),radial-gradient(circle_at_bottom_left,rgba(34,197,94,0.10),transparent_30%)] px-5 py-4">
        <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/6 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.24em] text-white/70">
          <Sparkles className="h-3.5 w-3.5 text-primary" />
          {eyebrow}
        </div>
        <h3 className="text-lg font-semibold text-white">{title}</h3>
        <p className="mt-1 text-sm leading-6 text-slate-300/78">{description}</p>
      </div>
      <div className="p-5">
        {children}
      </div>
    </section>
  );
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
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [showPptViewer, setShowPptViewer] = useState(true);
  const dragStateRef = useRef<{
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);

  useEffect(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
    setIsDragging(false);
    dragStateRef.current = null;
  }, [selectedDiagram?.url]);

  useEffect(() => {
    if (!isDragging) return undefined;

    const handleMouseUp = () => {
      setIsDragging(false);
      dragStateRef.current = null;
    };

    window.addEventListener("mouseup", handleMouseUp);
    return () => window.removeEventListener("mouseup", handleMouseUp);
  }, [isDragging]);

  const hasContent =
    umlDiagrams.length > 0 ||
    Boolean(pptUrl) ||
    isGeneratingUml ||
    isGeneratingPpt;
  const canEmbedViewer = useMemo(() => Boolean(viewerUrl), [viewerUrl]);

  if (!hasContent) return null;

  const handleZoomIn = () => {
    setZoom((value) => clampZoom(value + UML_ZOOM_STEP));
  };

  const handleZoomOut = () => {
    setZoom((value) => {
      const next = clampZoom(value - UML_ZOOM_STEP);
      if (next <= 1) {
        setPan({ x: 0, y: 0 });
      }
      return next;
    });
  };

  const handleResetView = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
    setIsDragging(false);
    dragStateRef.current = null;
  };

  const handleDiagramWheel = (event: ReactWheelEvent<HTMLDivElement>) => {
    event.preventDefault();
    setZoom((value) => {
      const delta = event.deltaY < 0 ? UML_ZOOM_STEP : -UML_ZOOM_STEP;
      const next = clampZoom(value + delta);
      if (next <= 1) {
        setPan({ x: 0, y: 0 });
      }
      return next;
    });
  };

  const handleDiagramMouseDown = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (event.button !== 0 || zoom <= 1) return;
    event.preventDefault();
    dragStateRef.current = {
      startX: event.clientX,
      startY: event.clientY,
      originX: pan.x,
      originY: pan.y,
    };
    setIsDragging(true);
  };

  const handleDiagramMouseMove = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (!dragStateRef.current) return;
    const nextX =
      dragStateRef.current.originX +
      (event.clientX - dragStateRef.current.startX) * UML_DRAG_DAMPING;
    const nextY =
      dragStateRef.current.originY +
      (event.clientY - dragStateRef.current.startY) * UML_DRAG_DAMPING;
    setPan({ x: nextX, y: nextY });
  };

  return (
    <>
      <style>{`
        @keyframes planner-bg-pulse {
          0%, 100% { opacity: 0.45; transform: translateX(-6%); }
          50% { opacity: 0.9; transform: translateX(12%); }
        }
      `}</style>
      <div className="space-y-4 animate-fade-in-up">
        {(isGeneratingUml || isGeneratingPpt) && (
          <div className="overflow-hidden rounded-[24px] border border-primary/15 bg-[linear-gradient(180deg,rgba(30,41,59,0.92),rgba(15,23,42,0.76))] shadow-[0_18px_42px_rgba(15,23,42,0.24)] backdrop-blur-xl">
            <div className="flex items-center gap-3 px-5 py-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-primary/20 bg-primary/10">
                <Presentation className="h-4.5 w-4.5 text-primary" />
              </div>
              <div className="flex items-center gap-1">
                {[0, 1, 2].map((index) => (
                  <span
                    key={index}
                    className="h-2.5 w-2.5 rounded-full bg-primary animate-bounce"
                    style={{ animationDelay: `${index * 140}ms` }}
                  />
                ))}
              </div>
              <div>
                <p className="text-sm font-semibold text-white">
                  {isGeneratingPpt && isGeneratingUml
                    ? "Preparing presentation and UML assets"
                    : isGeneratingPpt
                      ? "Preparing presentation assets"
                      : "Preparing UML diagrams"}
                </p>
                <p className="text-xs text-slate-300/72">
                  CODEXA is generating reusable files for this project.
                </p>
              </div>
            </div>
            <div className="h-1 bg-white/5">
              <div
                className="h-full w-1/2 rounded-full bg-[linear-gradient(90deg,hsl(var(--primary)),hsl(262_80%_60%))]"
                style={{ animation: "planner-bg-pulse 1.8s ease-in-out infinite" }}
              />
            </div>
          </div>
        )}

        {umlDiagrams.length > 0 && (
          <PanelFrame
            eyebrow="UML Gallery"
            title="Reusable system diagrams"
            description="Open any diagram in a focused viewer, zoom in, or download the final image."
          >
            <div className="mb-4 flex items-center justify-between gap-3 rounded-2xl border border-white/8 bg-white/5 px-4 py-3">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-slate-400">
                  Project
                </p>
                <p className="text-sm font-medium text-white">
                  {projectTitle || "Current project"}
                </p>
              </div>
              <div className="inline-flex items-center gap-2 rounded-full border border-emerald-400/15 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-300">
                <CheckCircle2 className="h-3.5 w-3.5" />
                {umlDiagrams.length} diagram{umlDiagrams.length === 1 ? "" : "s"} ready
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {umlDiagrams.map((diagram) => (
                <div
                  key={diagram.diagram_type}
                  className="group overflow-hidden rounded-2xl border border-white/10 bg-white/[0.04] transition-all duration-300 hover:-translate-y-0.5 hover:border-primary/35 hover:shadow-lg hover:shadow-primary/10"
                >
                  <button
                    type="button"
                    onClick={() => setSelectedDiagram(diagram)}
                    className="block w-full text-left"
                  >
                    <div className="aspect-[16/10] overflow-hidden bg-slate-950/40">
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
                        Click to inspect
                      </p>
                    </button>
                    <a
                      href={diagram.url}
                      download
                      target="_blank"
                      rel="noreferrer"
                      onClick={(event) => event.stopPropagation()}
                      className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-white/10 bg-white/5 text-slate-300 transition hover:border-primary/35 hover:bg-primary/10 hover:text-white"
                      aria-label={`Download ${prettyDiagramName(diagram.diagram_type)}`}
                    >
                      <Download className="h-4 w-4" />
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </PanelFrame>
        )}

        {(pptUrl || isGeneratingPpt) && (
          <PanelFrame
            eyebrow="Presentation"
            title="Downloadable project deck"
            description="Open the generated deck inline when a public URL is available, or download the .pptx directly."
          >
            <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="rounded-2xl border border-white/8 bg-white/5 px-4 py-3 text-sm text-slate-300/76">
                The deck is generated uniquely from the project description, structure, and reusable assets.
              </div>

              {pptUrl && (
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setShowPptViewer((value) => !value)}
                    className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium text-white transition hover:border-primary/35 hover:bg-primary/10"
                  >
                    <ExternalLink className="h-4 w-4" />
                    {showPptViewer ? "Hide PPT" : "View PPT"}
                  </button>
                  <a
                    href={pptUrl}
                    download
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium text-white transition hover:border-primary/35 hover:bg-primary/10"
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
                  <div className="overflow-hidden rounded-2xl border border-white/10 bg-black/20">
                    <iframe
                      title="Generated PPT Preview"
                      src={viewerUrl ?? undefined}
                      className="h-[520px] w-full border-0"
                    />
                  </div>
                ) : (
                  <div className="rounded-2xl border border-dashed border-white/12 bg-white/[0.04] px-5 py-6">
                    <div className="flex items-start gap-3">
                      <div className="rounded-2xl border border-white/10 bg-white/6 p-3">
                        <FileText className="h-5 w-5 text-primary" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-white">
                          Inline viewer needs a public PPT URL
                        </p>
                        <p className="mt-1 text-sm text-slate-300/76">
                          The presentation is ready to download. The embedded Google
                          Docs viewer will appear automatically when the backend is
                          reachable from a public host.
                        </p>
                      </div>
                    </div>
                  </div>
                )
              ) : null
            ) : (
              <div className="rounded-2xl border border-dashed border-white/12 bg-white/[0.04] px-5 py-6">
                <p className="text-sm text-slate-300/76">
                  Preparing the project deck...
                </p>
              </div>
            )}
          </PanelFrame>
        )}
      </div>

      <Dialog
        open={Boolean(selectedDiagram)}
        onOpenChange={(open) => {
          if (!open) setSelectedDiagram(null);
        }}
      >
        <DialogContent className="max-w-6xl border-border/60 bg-[hsl(var(--background)/0.98)] p-0 text-foreground">
          <DialogHeader className="border-b border-border/50 px-6 py-4">
            <DialogTitle>
              {prettyDiagramName(selectedDiagram?.diagram_type || "Diagram")}
            </DialogTitle>
          </DialogHeader>

          <div className="flex items-center justify-between gap-3 border-b border-border/50 px-6 py-3">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <ImageIcon className="h-4 w-4 text-primary" />
              Inspect and download the generated diagram.
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleZoomOut}
                className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-border/50 bg-muted/25 transition hover:border-primary/35 hover:bg-primary/10"
                aria-label="Zoom out"
              >
                <Minus className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={handleZoomIn}
                className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-border/50 bg-muted/25 transition hover:border-primary/35 hover:bg-primary/10"
                aria-label="Zoom in"
              >
                <Plus className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={handleResetView}
                className="inline-flex items-center gap-2 rounded-full border border-border/50 bg-muted/25 px-4 py-2 text-sm font-medium transition hover:border-primary/35 hover:bg-primary/10"
              >
                Reset
              </button>
              {selectedDiagram && (
                <a
                  href={selectedDiagram.url}
                  download
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 rounded-full border border-border/50 bg-muted/25 px-4 py-2 text-sm font-medium transition hover:border-primary/35 hover:bg-primary/10"
                >
                  <Download className="h-4 w-4" />
                  Download
                </a>
              )}
            </div>
          </div>

          <div className="max-h-[78vh] overflow-auto bg-muted/20 p-6">
            <div className="mb-3 px-1 text-xs text-muted-foreground">
              Use the mouse wheel to zoom and drag the diagram when zoomed in.
            </div>
            <div
              className="flex min-h-[62vh] items-center justify-center overflow-hidden rounded-3xl border border-border/50 bg-background/60 p-6"
              onWheel={handleDiagramWheel}
              onMouseDown={handleDiagramMouseDown}
              onMouseMove={handleDiagramMouseMove}
              onMouseUp={() => {
                setIsDragging(false);
                dragStateRef.current = null;
              }}
              onMouseLeave={() => {
                if (!isDragging) return;
                setIsDragging(false);
                dragStateRef.current = null;
              }}
            >
              {selectedDiagram && (
                <div
                  className={isDragging ? "cursor-grabbing select-none" : zoom > 1 ? "cursor-grab select-none" : "select-none"}
                  style={{ transform: `translate(${pan.x}px, ${pan.y}px)` }}
                >
                  <img
                    src={selectedDiagram.url}
                    alt={prettyDiagramName(selectedDiagram.diagram_type)}
                    draggable={false}
                    className="max-h-[68vh] w-auto origin-center transition-transform duration-150"
                    style={{ transform: `scale(${zoom})` }}
                  />
                </div>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
