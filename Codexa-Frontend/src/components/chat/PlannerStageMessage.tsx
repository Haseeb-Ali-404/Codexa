import { cn } from "@/lib/utils";
import {
  CheckCircle2,
  Circle,
  AlertCircle,
  RefreshCw,
  Brain,
  Layers,
  Link2,
  ShieldCheck,
  Wand2,
  GitBranch,
} from "lucide-react";

export type StageStatus = "idle" | "running" | "complete" | "warning" | "retrying";

export interface PipelineStage {
  stage: number;
  status: StageStatus;
  message?: string;
  output?: Record<string, unknown>;
  errors?: string[];
  warnings?: string[];
}

export interface PlannerPipelineState {
  stages: PipelineStage[];
  currentStage: number;
  isComplete: boolean;
  userPlan?: Record<string, unknown>;
  developerPlan?: Record<string, unknown>;
  planText?: string;
  planResult?: { title: string; steps: string[] };
}

const STAGE_META = [
  { label: "Understanding idea", icon: Brain, color: "text-violet-400", glow: "shadow-violet-500/40", ring: "ring-violet-500/30", bg: "bg-violet-500/10" },
  { label: "Designing structure", icon: Layers, color: "text-blue-400", glow: "shadow-blue-500/40", ring: "ring-blue-500/30", bg: "bg-blue-500/10" },
  { label: "Defining contracts", icon: GitBranch, color: "text-cyan-400", glow: "shadow-cyan-500/40", ring: "ring-cyan-500/30", bg: "bg-cyan-500/10" },
  { label: "Connecting modules", icon: Link2, color: "text-emerald-400", glow: "shadow-emerald-500/40", ring: "ring-emerald-500/30", bg: "bg-emerald-500/10" },
  { label: "Safety & finalizing", icon: ShieldCheck, color: "text-amber-400", glow: "shadow-amber-500/40", ring: "ring-amber-500/30", bg: "bg-amber-500/10" },
];

function BreathingDots() {
  return (
    <span className="flex items-center gap-[3px]">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1 h-1 rounded-full bg-primary"
          style={{ animation: `planner-breath 1.2s ease-in-out ${i * 0.2}s infinite` }}
        />
      ))}
    </span>
  );
}

function StageRow({ stage }: { stage: PipelineStage }) {
  const meta = STAGE_META[stage.stage - 1] ?? STAGE_META[0];
  const Icon = meta.icon;
  const isRunning = stage.status === "running";
  const isRetrying = stage.status === "retrying";
  const isDone = stage.status === "complete";
  const isWarning = stage.status === "warning";

  return (
    <div
      className={cn(
        "relative flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-500 overflow-hidden",
        isRunning && `border ring-1 ${meta.ring} border-transparent`,
        isDone && "opacity-70",
        isWarning && "border border-amber-500/20",
        !isRunning && !isWarning && "border border-transparent",
        stage.status === "idle" && "opacity-30",
      )}
    >
      {isRunning && (
        <div
          className={cn("absolute inset-0 rounded-xl", meta.bg, "opacity-40")}
          style={{ animation: "planner-bg-pulse 2s ease-in-out infinite" }}
        />
      )}

      <div
        className={cn(
          "relative shrink-0 w-6 h-6 rounded-full flex items-center justify-center z-10",
          isRunning && `${meta.bg} ring-1 ${meta.ring} shadow-md ${meta.glow}`,
          isDone && "bg-emerald-500/15",
          isRetrying && "bg-amber-500/15",
          isWarning && "bg-amber-500/15",
          stage.status === "idle" && "bg-muted/30",
        )}
      >
        {stage.status === "idle" && <Circle className="w-3 h-3 text-muted-foreground/50" />}
        {isRunning && <Icon className={cn("w-3 h-3", meta.color)} style={{ animation: "planner-breath 1.4s ease-in-out infinite" }} />}
        {isRetrying && <RefreshCw className="w-3 h-3 text-amber-400 animate-spin" />}
        {isDone && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />}
        {isWarning && <AlertCircle className="w-3 h-3 text-amber-400" />}

        {isRunning && (
          <span
            className={cn("absolute inset-0 rounded-full ring-1", meta.ring)}
            style={{ animation: "planner-ring-ping 1.6s ease-out infinite" }}
          />
        )}
      </div>

      <span
        className={cn(
          "text-[11px] font-medium flex-1 min-w-0 z-10 leading-tight",
          isRunning ? "text-foreground font-semibold" : "text-muted-foreground",
          isDone && "line-through decoration-muted-foreground/30",
        )}
      >
        {stage.message || meta.label}
      </span>

      <div className="z-10 shrink-0">
        {isRunning && <BreathingDots />}
        {isDone && <span className="text-[9px] text-emerald-400 font-semibold">OK</span>}
        {isWarning && <span className="text-[9px] text-amber-400">!</span>}
        {stage.status === "idle" && (
          <span className="text-[9px] text-muted-foreground/40 font-mono">{stage.stage}</span>
        )}
      </div>
    </div>
  );
}

interface Props {
  pipeline: PlannerPipelineState;
}

export function PlannerStageMessage({ pipeline }: Props) {
  const { stages, isComplete, planText, planResult } = pipeline;
  const doneCount = stages.filter((s) => s.status === "complete").length;
  const progress = (doneCount / stages.length) * 100;
  const hasAnyActivity = stages.some((s) => s.status !== "idle");
  const activeStage = stages.find((s) => s.status === "running");

  return (
    <>
      <style>{`
        @keyframes planner-breath {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.6; transform: scale(0.85); }
        }
        @keyframes planner-bg-pulse {
          0%, 100% { opacity: 0.35; }
          50% { opacity: 0.6; }
        }
        @keyframes planner-ring-ping {
          0%   { transform: scale(1); opacity: 0.7; }
          70%  { transform: scale(1.9); opacity: 0; }
          100% { transform: scale(1.9); opacity: 0; }
        }
      `}</style>

      <div className="space-y-2.5 text-sm">
        <div className="flex items-center gap-2">
          <div
            className={cn(
              "w-7 h-7 rounded-lg flex items-center justify-center",
              isComplete ? "bg-emerald-500/15" : "bg-primary/15",
            )}
          >
            {isComplete ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            ) : (
              <Wand2 className="w-4 h-4 text-primary" style={{ animation: "planner-breath 1.8s ease-in-out infinite" }} />
            )}
          </div>
          <div className="min-w-0">
            <p className="font-semibold text-foreground text-xs leading-tight">
              {isComplete
                ? "Planning complete"
                : activeStage
                  ? `Stage ${activeStage.stage} of ${stages.length} - ${activeStage.message || STAGE_META[activeStage.stage - 1]?.label}`
                  : "Analyzing your request..."}
            </p>
            {hasAnyActivity && (
              <p className="text-[10px] text-muted-foreground">{doneCount} of {stages.length} stages done</p>
            )}
          </div>
        </div>

        {hasAnyActivity && (
          <div className="h-1 bg-muted/40 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-700"
              style={{
                width: `${isComplete ? 100 : progress}%`,
                background: isComplete
                  ? "hsl(var(--emerald, 152 76% 45%))"
                  : "linear-gradient(90deg, hsl(var(--primary)), hsl(262 80% 60%))",
              }}
            />
          </div>
        )}

        <div className="space-y-0.5">
          {stages.map((stage) => (
            <StageRow key={stage.stage} stage={stage} />
          ))}
        </div>

        {planText && !planResult && (
          <div className="p-2.5 rounded-xl bg-muted/30 border border-border/40 font-mono text-[10px] text-muted-foreground leading-relaxed max-h-28 overflow-y-auto whitespace-pre-wrap">
            {planText}
            <span
              className="inline-block w-0.5 h-3 bg-primary ml-0.5 align-middle"
              style={{ animation: "planner-breath 0.9s ease-in-out infinite" }}
            />
          </div>
        )}

        {planResult && (
          <div className="space-y-1.5">
            <p className="font-semibold text-foreground text-xs px-1">{planResult.title}</p>
            <div className="space-y-1">
              {planResult.steps.map((step, i) => (
                <div key={i} className="flex gap-2 items-start px-1">
                  <span className="shrink-0 w-4 h-4 rounded-full bg-primary/15 text-primary text-[9px] font-bold flex items-center justify-center mt-0.5">
                    {i + 1}
                  </span>
                  <p className="text-[11px] text-muted-foreground leading-relaxed">{step}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
