import { cn } from "@/lib/utils";
import {
  Brain,
  GitBranch,
  Code2,
  Package,
  Rocket,
  CheckCircle2,
  Circle,
  Loader2,
} from "lucide-react";

export type DeveloperStageStatus = "idle" | "running" | "complete" | "error";

export interface DeveloperPipelineStage {
  stage: number;
  status: DeveloperStageStatus;
  message?: string;
}

export interface DeveloperPipelineState {
  stages: DeveloperPipelineStage[];
  currentStage: number;
  isComplete: boolean;
  totalTiers?: number;
  currentTier?: number;
  totalFiles?: number;
  completedFiles?: number;
  currentBatchLabel?: string;
  recentUpdates?: string[];
  assembledFiles?: number;
  deliveryChunksReceived?: number;
  deliveryChunksTotal?: number;
  isParallel?: boolean;
}

const STAGE_META = [
  {
    label: "Planning structure",
    icon: Brain,
    color: "text-sky-400",
    glow: "shadow-sky-500/30",
    ring: "ring-sky-500/30",
    bg: "bg-sky-500/10",
  },
  {
    label: "Preparing tiers",
    icon: GitBranch,
    color: "text-cyan-400",
    glow: "shadow-cyan-500/30",
    ring: "ring-cyan-500/30",
    bg: "bg-cyan-500/10",
  },
  {
    label: "Generating files",
    icon: Code2,
    color: "text-indigo-400",
    glow: "shadow-indigo-500/30",
    ring: "ring-indigo-500/30",
    bg: "bg-indigo-500/10",
  },
  {
    label: "Assembling workspace",
    icon: Package,
    color: "text-amber-400",
    glow: "shadow-amber-500/30",
    ring: "ring-amber-500/30",
    bg: "bg-amber-500/10",
  },
  {
    label: "Delivering output",
    icon: Rocket,
    color: "text-emerald-400",
    glow: "shadow-emerald-500/30",
    ring: "ring-emerald-500/30",
    bg: "bg-emerald-500/10",
  },
];

function StageRow({ stage }: { stage: DeveloperPipelineStage }) {
  const meta = STAGE_META[stage.stage - 1] ?? STAGE_META[0];
  const Icon = meta.icon;
  const isRunning = stage.status === "running";
  const isDone = stage.status === "complete";

  return (
    <div
      className={cn(
        "relative flex items-center gap-3 rounded-xl border px-3 py-2.5 transition-all duration-500 overflow-hidden",
        isRunning
          ? `${meta.bg} ring-1 ${meta.ring} border-transparent shadow-sm ${meta.glow}`
          : "border-border/40",
        isDone && "opacity-75",
        stage.status === "idle" && "opacity-35",
      )}
    >
      <div
        className={cn(
          "relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full",
          isRunning && `${meta.bg} ring-1 ${meta.ring}`,
          isDone && "bg-emerald-500/15",
          stage.status === "idle" && "bg-muted/40",
        )}
      >
        {stage.status === "idle" && <Circle className="h-3 w-3 text-muted-foreground/60" />}
        {isRunning && (
          <Icon
            className={cn("h-3.5 w-3.5", meta.color)}
            style={{ animation: "developer-breath 1.4s ease-in-out infinite" }}
          />
        )}
        {isDone && <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />}
      </div>

      <div className="relative z-10 min-w-0 flex-1">
        <p
          className={cn(
            "text-[11px] leading-tight",
            isRunning ? "font-semibold text-foreground" : "text-muted-foreground",
            isDone && "line-through decoration-muted-foreground/40",
          )}
        >
          {stage.message || meta.label}
        </p>
      </div>

      <div className="relative z-10 shrink-0">
        {isRunning ? (
          <Loader2 className={cn("h-3 w-3 animate-spin", meta.color)} />
        ) : isDone ? (
          <span className="text-[9px] font-semibold text-emerald-400">OK</span>
        ) : (
          <span className="font-mono text-[9px] text-muted-foreground/50">{stage.stage}</span>
        )}
      </div>
    </div>
  );
}

function MetricPill({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "active" | "success";
}) {
  return (
    <div
      className={cn(
        "rounded-full border px-2.5 py-1 text-[10px] font-medium",
        tone === "active" && "border-primary/30 bg-primary/10 text-primary",
        tone === "success" && "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
        tone === "default" && "border-border/50 bg-muted/30 text-muted-foreground",
      )}
    >
      <span className="opacity-80">{label}</span>{" "}
      <span className="text-foreground">{value}</span>
    </div>
  );
}

interface Props {
  pipeline: DeveloperPipelineState;
}

export function DeveloperStageMessage({ pipeline }: Props) {
  const completedStages = pipeline.stages.filter((stage) => stage.status === "complete").length;
  const activeStage = pipeline.stages.find((stage) => stage.status === "running");

  const stagePct = completedStages / Math.max(pipeline.stages.length, 1);
  const filePct =
    pipeline.totalFiles && pipeline.totalFiles > 0
      ? (pipeline.completedFiles ?? 0) / pipeline.totalFiles
      : 0;
  const deliveryPct =
    pipeline.deliveryChunksTotal && pipeline.deliveryChunksTotal > 0
      ? (pipeline.deliveryChunksReceived ?? 0) / pipeline.deliveryChunksTotal
      : 0;
  const activePct = pipeline.currentStage === 5 ? deliveryPct : filePct;
  const progress = Math.min(
    100,
    Math.round((stagePct + activePct / Math.max(pipeline.stages.length, 1)) * 100),
  );

  const updates = (pipeline.recentUpdates ?? []).slice(-3).reverse();

  return (
    <>
      <style>{`
        @keyframes developer-breath {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.62; transform: scale(0.88); }
        }
        @keyframes developer-pulse {
          0%, 100% { opacity: 0.45; }
          50% { opacity: 0.72; }
        }
      `}</style>

      <div className="space-y-3 text-sm">
        <div className="flex items-start gap-3">
          <div
            className={cn(
              "relative flex h-8 w-8 shrink-0 items-center justify-center rounded-xl",
              pipeline.isComplete ? "bg-emerald-500/15" : "bg-primary/15",
            )}
          >
            {pipeline.isComplete ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            ) : (
              <Code2
                className="h-4 w-4 text-primary"
                style={{ animation: "developer-breath 1.6s ease-in-out infinite" }}
              />
            )}
            {!pipeline.isComplete && (
              <span
                className="absolute inset-0 rounded-xl bg-primary/10"
                style={{ animation: "developer-pulse 1.8s ease-in-out infinite" }}
              />
            )}
          </div>

          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold leading-tight text-foreground">
              {pipeline.isComplete
                ? "Developer output ready"
                : activeStage
                  ? `Stage ${activeStage.stage} of ${pipeline.stages.length} - ${activeStage.message || STAGE_META[activeStage.stage - 1]?.label}`
                  : "Developer agent is getting started"}
            </p>
            <p className="mt-1 text-[10px] text-muted-foreground">
              {pipeline.isComplete
                ? "The generated project has been packaged and delivered."
                : pipeline.currentBatchLabel || "Translating the plan into working project files."}
            </p>
          </div>
        </div>

        <div className="h-1.5 overflow-hidden rounded-full bg-muted/40">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${pipeline.isComplete ? 100 : progress}%`,
              background: pipeline.isComplete
                ? "linear-gradient(90deg, hsl(152 76% 45%), hsl(160 84% 39%))"
                : "linear-gradient(90deg, hsl(var(--primary)), hsl(217 91% 60%))",
            }}
          />
        </div>

        <div className="flex flex-wrap gap-2">
          {pipeline.totalTiers ? (
            <MetricPill
              label="Tier"
              value={`${pipeline.currentTier ?? 0}/${pipeline.totalTiers}`}
              tone={pipeline.currentStage === 3 ? "active" : "default"}
            />
          ) : null}
          {pipeline.totalFiles ? (
            <MetricPill
              label="Files"
              value={`${pipeline.completedFiles ?? 0}/${pipeline.totalFiles}`}
              tone={pipeline.isComplete ? "success" : pipeline.currentStage >= 3 ? "active" : "default"}
            />
          ) : null}
          {pipeline.deliveryChunksTotal ? (
            <MetricPill
              label="Chunks"
              value={`${pipeline.deliveryChunksReceived ?? 0}/${pipeline.deliveryChunksTotal}`}
              tone={pipeline.currentStage === 5 ? "active" : pipeline.isComplete ? "success" : "default"}
            />
          ) : null}
          {pipeline.isParallel ? <MetricPill label="Mode" value="Parallel" tone="default" /> : null}
        </div>

        <div className="space-y-1">
          {pipeline.stages.map((stage) => (
            <StageRow key={stage.stage} stage={stage} />
          ))}
        </div>

        {updates.length > 0 && (
          <div className="rounded-xl border border-border/40 bg-muted/20 p-2.5">
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              Live updates
            </p>
            <div className="space-y-1.5">
              {updates.map((update, index) => (
                <div key={`${update}-${index}`} className="flex items-start gap-2">
                  <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-primary/80" />
                  <p className="text-[11px] leading-relaxed text-muted-foreground">{update}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
