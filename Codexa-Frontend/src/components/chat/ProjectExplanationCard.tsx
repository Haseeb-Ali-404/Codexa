import { cn } from "@/lib/utils";
import {
  Sparkles, CheckCircle2, Layers, Server, Database,
  Link2, MonitorSmartphone, ChevronDown, ExternalLink,
} from "lucide-react";
import { useState } from "react";

interface ComponentBreakdown {
  frontend?: string;
  backend?: string;
  database?: string;
  integration?: string;
  [key: string]: string | undefined;
}

interface Props {
  data: Record<string, unknown>;
  projectTitle?: string;
}

// ── helpers ───────────────────────────────────────────────────────────────────

const LAYER_META = [
  {
    key: "frontend",
    label: "Frontend",
    icon: MonitorSmartphone,
    accent: "text-blue-400",
    border: "border-blue-500/20",
    bg: "bg-blue-500/8",
    dot: "bg-blue-400",
    ring: "ring-blue-500/20",
  },
  {
    key: "backend",
    label: "Backend",
    icon: Server,
    accent: "text-violet-400",
    border: "border-violet-500/20",
    bg: "bg-violet-500/8",
    dot: "bg-violet-400",
    ring: "ring-violet-500/20",
  },
  {
    key: "database",
    label: "Database",
    icon: Database,
    accent: "text-emerald-400",
    border: "border-emerald-500/20",
    bg: "bg-emerald-500/8",
    dot: "bg-emerald-400",
    ring: "ring-emerald-500/20",
  },
  {
    key: "integration",
    label: "Integration",
    icon: Link2,
    accent: "text-amber-400",
    border: "border-amber-500/20",
    bg: "bg-amber-500/8",
    dot: "bg-amber-400",
    ring: "ring-amber-500/20",
  },
] as const;

function LayerCard({
  meta,
  text,
  defaultOpen,
}: {
  meta: typeof LAYER_META[number];
  text: string;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const Icon = meta.icon;

  return (
    <div className={cn("rounded-xl border overflow-hidden transition-all", meta.border)}>
      <button
        onClick={() => setOpen(o => !o)}
        className={cn(
          "w-full flex items-center gap-2.5 px-3 py-2.5 text-left transition-colors",
          open ? meta.bg : "bg-transparent hover:bg-muted/20",
        )}
      >
        <div className={cn(
          "w-6 h-6 rounded-lg flex items-center justify-center shrink-0",
          meta.bg, "border", meta.border,
        )}>
          <Icon className={cn("w-3.5 h-3.5", meta.accent)} />
        </div>
        <span className="text-[11px] font-semibold text-foreground flex-1">{meta.label}</span>
        <ChevronDown className={cn(
          "w-3.5 h-3.5 text-muted-foreground/60 transition-transform duration-200",
          open && "rotate-180",
        )} />
      </button>

      {open && (
        <div className="px-3 pb-3 pt-1 border-t border-border/20">
          <p className="text-[11px] text-muted-foreground leading-relaxed whitespace-pre-line">
            {text}
          </p>
        </div>
      )}
    </div>
  );
}

// ── main export ───────────────────────────────────────────────────────────────

export function ProjectExplanationCard({ data, projectTitle }: Props) {
  const explanation = (
    data.explanation || data.overview || data.description || data.summary || ""
  ) as string;

  const breakdown = (data.component_breakdown || {}) as ComponentBreakdown;

  // Determine a display title
  const displayTitle =
    projectTitle ||
    (data.project_name as string) ||
    (data.title as string) ||
    (data.name as string) ||
    "Your Project";

  const layers = LAYER_META.filter(m => !!breakdown[m.key]);

  return (
    <div className="space-y-3 text-sm">

      {/* ── Header ── */}
      <div className="flex items-start gap-3">
        <div className="relative shrink-0 mt-0.5">
          <div className="w-9 h-9 rounded-2xl bg-gradient-to-br from-primary/20 via-violet-500/15 to-blue-500/10 border border-primary/20 flex items-center justify-center">
            <Sparkles className="w-4 h-4 text-primary" />
          </div>
          <div className="absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-emerald-500 border-2 border-background flex items-center justify-center">
            <CheckCircle2 className="w-2 h-2 text-white" />
          </div>
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-bold text-foreground text-sm leading-tight">{displayTitle}</p>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400" />
            <span className="text-[10px] text-emerald-400 font-medium">Generated &amp; ready</span>
          </div>
        </div>
      </div>

      {/* ── Divider ── */}
      <div className="h-px bg-gradient-to-r from-transparent via-border/50 to-transparent" />

      {/* ── Overview ── */}
      {explanation && (
        <div className="space-y-1">
          <p className="text-[9px] font-semibold uppercase tracking-widest text-muted-foreground/60 flex items-center gap-1.5">
            <Layers className="w-3 h-3" /> Architecture Overview
          </p>
          <p className="text-[11px] text-muted-foreground leading-relaxed">
            {explanation.length > 400
              ? explanation.slice(0, 400) + "…"
              : explanation}
          </p>
        </div>
      )}

      {/* ── Stack layer tabs ── */}
      {layers.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[9px] font-semibold uppercase tracking-widest text-muted-foreground/60 flex items-center gap-1.5">
            <Server className="w-3 h-3" /> Component Breakdown
          </p>
          {layers.map((meta, i) => (
            <LayerCard
              key={meta.key}
              meta={meta}
              text={breakdown[meta.key] ?? ""}
              defaultOpen={i === 0}
            />
          ))}
        </div>
      )}

      {/* ── Footer ── */}
      <div className="flex items-center gap-2 pt-1 border-t border-border/25">
        <div className="flex items-center gap-2 flex-1 flex-wrap">
          {LAYER_META.map(m => (
            breakdown[m.key] ? (
              <div key={m.key} className="flex items-center gap-1">
                <span className={cn("w-1.5 h-1.5 rounded-full", m.dot)} />
                <span className="text-[9px] text-muted-foreground/60">{m.label}</span>
              </div>
            ) : null
          ))}
        </div>
        <div className="flex items-center gap-1 text-[10px] text-primary/80 font-medium shrink-0">
          <ExternalLink className="w-3 h-3" />
          Preview
        </div>
      </div>
    </div>
  );
}
