import { cn } from "@/lib/utils";
import { ShieldCheck, ShieldAlert, Loader2, CheckCircle2, XCircle, Scan } from "lucide-react";

const CHECKS = [
  "Verifying file structure",
  "Checking API contracts",
  "Validating imports & exports",
  "Checking component wiring",
  "Inspecting environment config",
];

interface Props {
  passed?: boolean | null;
  architectureData?: Record<string, unknown>;
}

export function ValidatorMessage({ passed, architectureData }: Props) {
  const isPending = passed === null || passed === undefined;
  const isRunning = isPending && !architectureData;

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2.5">
        <div className={cn(
          "w-8 h-8 rounded-xl flex items-center justify-center shrink-0",
          isPending && "bg-amber-500/15",
          passed === true && "bg-emerald-500/15",
          passed === false && "bg-red-500/15",
        )}>
          {isPending && <Scan className="w-4 h-4 text-amber-400 animate-pulse" />}
          {passed === true && <ShieldCheck className="w-4 h-4 text-emerald-400" />}
          {passed === false && <ShieldAlert className="w-4 h-4 text-red-400" />}
        </div>
        <div>
          <p className="text-xs font-semibold text-foreground">
            {isPending ? "Validating project…" : passed ? "Validation passed" : "Issues found — auto-fixing"}
          </p>
          <p className="text-[10px] text-muted-foreground">
            {isPending ? "Running integrity checks" : passed ? "All checks passed" : "Applying automatic fixes"}
          </p>
        </div>
      </div>

      {/* Animated checks (while running) */}
      {isRunning && (
        <div className="space-y-1">
          {CHECKS.map((check, i) => (
            <div key={check} className="flex items-center gap-2 px-1"
              style={{ animationDelay: `${i * 300}ms` }}>
              <Loader2
                className="w-3 h-3 text-amber-400 animate-spin shrink-0"
                style={{ animationDelay: `${i * 150}ms` }}
              />
              <span className="text-[10px] text-muted-foreground">{check}</span>
            </div>
          ))}
        </div>
      )}

      {/* Result checks (done) */}
      {!isPending && (
        <div className="space-y-1">
          {CHECKS.map((check) => (
            <div key={check} className="flex items-center gap-2 px-1">
              {passed
                ? <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
                : <XCircle className="w-3 h-3 text-amber-400 shrink-0" />}
              <span className="text-[10px] text-muted-foreground">{check}</span>
            </div>
          ))}
        </div>
      )}

      {/* Result badge */}
      {!isPending && (
        <div className={cn(
          "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10px] font-semibold border",
          passed
            ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
            : "bg-amber-500/10 border-amber-500/30 text-amber-400",
        )}>
          {passed
            ? <><CheckCircle2 className="w-3 h-3" /> Project is ready to preview</>
            : <><ShieldAlert className="w-3 h-3" /> Fixes applied automatically</>}
        </div>
      )}
    </div>
  );
}
