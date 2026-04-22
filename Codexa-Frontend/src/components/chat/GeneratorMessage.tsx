import { cn } from "@/lib/utils";
import { Code2, CheckCircle2, Loader2, FileCode, Cpu } from "lucide-react";

export interface GeneratorProgress {
  received: number;
  total: number;
  done: boolean;
}

const CODE_LINES = [
  "const App = () => {",
  "  const [data, setData] = useState([])",
  "  useEffect(() => { fetch('/api') }, [])",
  "  return <Dashboard data={data} />",
  "}",
  "router = APIRouter()",
  "@router.get('/items')",
  "async def get_items(db = Depends(get_db)):",
  "  return await db.find({})",
  "export default defineConfig({ plugins: [react()] })",
];

interface Props {
  progress?: GeneratorProgress;
  className?: string;
}

export function GeneratorMessage({ progress, className }: Props) {
  const pct = progress && progress.total > 0
    ? Math.round((progress.received / progress.total) * 100)
    : 0;
  const isDone = progress?.done ?? false;

  return (
    <div className={cn("space-y-3", className)}>
      {/* Header */}
      <div className="flex items-center gap-2.5">
        <div className={cn(
          "w-8 h-8 rounded-xl flex items-center justify-center shrink-0",
          isDone ? "bg-emerald-500/15" : "bg-indigo-500/15",
        )}>
          {isDone
            ? <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            : <Cpu className="w-4 h-4 text-indigo-400 animate-pulse" />}
        </div>
        <div className="min-w-0">
          <p className="text-xs font-semibold text-foreground">
            {isDone ? "Project generated" : "Generating project…"}
          </p>
          <p className="text-[10px] text-muted-foreground">
            {isDone
              ? "All files written successfully"
              : progress && progress.total > 0
                ? `Receiving data… ${pct}%`
                : "Building your application"}
          </p>
        </div>
      </div>

      {/* Animated code rain (only while generating) */}
      {!isDone && (
        <div className="relative rounded-xl bg-black/40 border border-white/5 overflow-hidden h-28 font-mono text-[9px] leading-5">
          <div className="absolute inset-0 animate-code-scroll select-none pointer-events-none px-3 pt-2 space-y-0.5">
            {[...CODE_LINES, ...CODE_LINES].map((line, i) => (
              <div key={i} className={cn(
                "whitespace-nowrap overflow-hidden",
                i % 3 === 0 ? "text-violet-400" : i % 3 === 1 ? "text-cyan-400/70" : "text-emerald-400/50",
              )}>
                {line}
              </div>
            ))}
          </div>
          {/* Fade bottom */}
          <div className="absolute bottom-0 left-0 right-0 h-10 bg-gradient-to-t from-black/60 to-transparent" />
          {/* Scan line */}
          <div className="absolute left-0 right-0 h-px bg-primary/30 animate-scan-line" />
        </div>
      )}

      {/* Progress bar */}
      {progress && progress.total > 0 && (
        <div className="space-y-1">
          <div className="h-1.5 bg-muted/50 rounded-full overflow-hidden">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-300",
                isDone
                  ? "bg-emerald-400"
                  : "bg-gradient-to-r from-indigo-500 to-violet-500"
              )}
              style={{ width: isDone ? "100%" : `${pct}%` }}
            />
          </div>
        </div>
      )}

      {/* File badges (done state) */}
      {isDone && (
        <div className="flex flex-wrap gap-1.5">
          {["React", "FastAPI", "MongoDB", "Tailwind", "TypeScript"].map(tech => (
            <span key={tech} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary/10 border border-primary/20 text-[10px] font-medium text-primary">
              <FileCode className="w-2.5 h-2.5" />
              {tech}
            </span>
          ))}
        </div>
      )}

      {/* Loading dots (before first chunk) */}
      {!isDone && (!progress || progress.total === 0) && (
        <div className="flex items-center gap-1.5">
          <Loader2 className="w-3 h-3 text-muted-foreground animate-spin" />
          <span className="text-[10px] text-muted-foreground">Compiling files…</span>
        </div>
      )}
    </div>
  );
}
