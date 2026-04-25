import { cn } from "@/lib/utils";
import {
  ShieldCheck,
  ShieldAlert,
  Loader2,
  CheckCircle2,
  XCircle,
  Scan,
} from "lucide-react";

const CHECKS = [
  "Verifying file structure",
  "Checking API contracts",
  "Validating imports & exports",
  "Checking component wiring",
  "Inspecting environment config",
];

export interface DebuggerState {
  status: "running" | "warning" | "complete";
  currentStep?: string;
  recentUpdates?: string[];
  filesProcessed?: number;
  filesFixed?: number;
  issuesFound?: number;
  isComplete?: boolean;
}

interface Props {
  passed?: boolean | null;
  architectureData?: Record<string, unknown>;
  debuggerState?: DebuggerState;
}

export function ValidatorMessage({
  passed,
  architectureData,
  debuggerState,
}: Props) {
  const isPending = passed === null || passed === undefined;
  const effectiveRunning = (debuggerState?.status ?? "running") === "running" && isPending && !architectureData;
  const updates = debuggerState?.recentUpdates || [];

  const title = effectiveRunning
    ? "Validating project..."
    : passed
      ? "Validation passed"
      : "Issues found - auto-fixing";

  const subtitle = effectiveRunning
    ? debuggerState?.currentStep || "Running integrity checks"
    : passed
      ? "All checks passed"
      : "Applying automatic fixes";

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2.5">
        <div
          className={cn(
            "w-8 h-8 rounded-xl flex items-center justify-center shrink-0",
            effectiveRunning && "bg-amber-500/15",
            passed === true && "bg-emerald-500/15",
            passed === false && "bg-red-500/15",
          )}
        >
          {effectiveRunning && <Scan className="w-4 h-4 text-amber-400 animate-pulse" />}
          {passed === true && <ShieldCheck className="w-4 h-4 text-emerald-400" />}
          {passed === false && <ShieldAlert className="w-4 h-4 text-red-400" />}
        </div>
        <div>
          <p className="text-xs font-semibold text-foreground">{title}</p>
          <p className="text-[10px] text-muted-foreground">{subtitle}</p>
        </div>
      </div>

      {effectiveRunning && (
        <div className="space-y-1">
          {CHECKS.map((check, i) => (
            <div
              key={check}
              className="flex items-center gap-2 px-1"
              style={{ animationDelay: `${i * 300}ms` }}
            >
              <Loader2
                className="w-3 h-3 text-amber-400 animate-spin shrink-0"
                style={{ animationDelay: `${i * 150}ms` }}
              />
              <span className="text-[10px] text-muted-foreground">{check}</span>
            </div>
          ))}
        </div>
      )}

      {updates.length > 0 && (
        <div className="space-y-1.5 rounded-2xl border border-border/60 bg-background/35 px-3 py-2">
          {updates.map((update) => (
            <div key={update} className="text-[10px] leading-relaxed text-muted-foreground">
              {update}
            </div>
          ))}
        </div>
      )}

      {(debuggerState?.filesProcessed ||
        debuggerState?.filesFixed ||
        debuggerState?.issuesFound) ? (
        <div className="flex flex-wrap gap-2">
          {debuggerState?.filesProcessed ? (
            <span className="rounded-full border border-border/70 px-2 py-1 text-[10px] text-muted-foreground">
              Files scanned: {debuggerState.filesProcessed}
            </span>
          ) : null}
          {debuggerState?.filesFixed ? (
            <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-400">
              Files fixed: {debuggerState.filesFixed}
            </span>
          ) : null}
          {debuggerState?.issuesFound ? (
            <span className="rounded-full border border-border/70 px-2 py-1 text-[10px] text-muted-foreground">
              Issues: {debuggerState.issuesFound}
            </span>
          ) : null}
        </div>
      ) : null}

      {!effectiveRunning && !isPending && (
        <div className="space-y-1">
          {CHECKS.map((check) => (
            <div key={check} className="flex items-center gap-2 px-1">
              {passed ? (
                <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
              ) : (
                <XCircle className="w-3 h-3 text-amber-400 shrink-0" />
              )}
              <span className="text-[10px] text-muted-foreground">{check}</span>
            </div>
          ))}
        </div>
      )}

      {!effectiveRunning && !isPending && (
        <div
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[10px] font-semibold",
            passed
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
              : "border-amber-500/30 bg-amber-500/10 text-amber-400",
          )}
        >
          {passed ? (
            <>
              <CheckCircle2 className="w-3 h-3" /> Project is ready to preview
            </>
          ) : (
            <>
              <ShieldAlert className="w-3 h-3" /> Fixes applied automatically
            </>
          )}
        </div>
      )}
    </div>
  );
}
