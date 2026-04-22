import { cn } from "@/lib/utils";
import {
  User,
  Sparkles,
  Copy,
  Check,
  ThumbsUp,
  ThumbsDown,
  RotateCcw,
  FileText,
} from "lucide-react";
import { CodeBlock } from "./CodeBlock";
import { useState, useEffect, useMemo, Fragment } from "react";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";
import {
  rehypeSearchHighlight,
  escapeRegExp,
} from "@/lib/rehypeSearchHighlight";
import { PlannerStageMessage } from "./PlannerStageMessage";
import type { PlannerPipelineState } from "./PlannerStageMessage";
import { GeneratorMessage } from "./GeneratorMessage";
import type { GeneratorProgress } from "./GeneratorMessage";
import { ValidatorMessage } from "./ValidatorMessage";
import { ProjectExplanationCard } from "./ProjectExplanationCard";

interface ChatMessageProps {
  message: {
    id: string;
    role: "user" | "assistant";
    title?: string;
    agent: "developer" | "debugger" | "planner" | "generator" | "validator" | "architect" | "chat" | string | null;
    content: string;
    createdAt?: string | number;
    pipeline?: PlannerPipelineState;
    generatorProgress?: GeneratorProgress;
    validationPassed?: boolean | null;
    architectureData?: Record<string, unknown>;
    code?: {
      language: string;
      content: string;
    };
    attachments?: Array<{
      id: string;
      name: string;
      kind: "image" | "file";
      mimeType: string;
      url: string;
    }>;
  };
  index: number;
  /** Debounced query from navbar chat search — highlights matches in body text */
  searchHighlight?: string;
}

function renderHighlightedPlain(
  text: string,
  query: string | undefined,
  isUserBubble: boolean,
) {
  const q = query?.trim();
  if (!q || !text) return text;
  const re = new RegExp(`(${escapeRegExp(q)})`, "gi");
  const parts = text.split(re);
  const qLower = q.toLowerCase();
  return parts.map((part, i) =>
    part !== "" && part.toLowerCase() === qLower ? (
      <mark
        key={i}
        className={cn(
          "chat-search-mark",
          isUserBubble && "chat-search-mark-user",
        )}
      >
        {part}
      </mark>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

export function ChatMessage({ message, index, searchHighlight }: ChatMessageProps) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);
  const [planSteps, setPlanSteps] = useState<string[]>([]);
  const [title, setTitle] = useState<string | null>(null);
  const [parsedCode, setParsedCode] = useState(message.code || null);

  // Utility: format developer code safely
  function formatCodeString(raw: string, language = "html") {
    if (!raw) return { language, content: "" };

    let cleaned = raw.trim();

    if (
      (cleaned.startsWith('"') && cleaned.endsWith('"')) ||
      (cleaned.startsWith("'") && cleaned.endsWith("'"))
    ) {
      cleaned = cleaned.slice(1, -1);
    }

    cleaned = cleaned.replace(/\\n/g, "\n").replace(/\\"/g, '"');

    return { language, content: cleaned };
  }

  // Parse planner + developer + architect content
  useEffect(() => {
    if (message.agent === "planner") {
      try {
        const parsed = JSON.parse(message.content);
        setTitle(parsed.title || null);
        setPlanSteps(parsed.plan || parsed.steps || []);
      } catch {
        console.error("Invalid planner JSON:", message.content);
      }
    }

    if (message.agent === "architect" && message.architectureData) {
      const d = message.architectureData;
      const t = (d.project_name || d.title || d.name || message.title || null) as string | null;
      setTitle(t);
    }

    if (message.agent === "developer") {
      try {
        const formatted = formatCodeString(message.content, "html");
        setParsedCode(formatted);
      } catch {
        console.error("Developer code formatting failed.");
      }
    }
  }, [message]);

  const searchRehypePlugins = useMemo(() => {
    const q = searchHighlight?.trim();
    if (!q) return [];
    return [
      [rehypeSearchHighlight, { query: searchHighlight ?? "", variant: isUser ? "user" : "default" }],
    ] as const;
  }, [searchHighlight, isUser]);

  // Copy message
  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    toast.success("Copied to clipboard");
    setTimeout(() => setCopied(false), 2000);
  };

  const handleFeedback = (type: "up" | "down") => {
    setFeedback(type);
    toast.success(
      type === "up" ? "Thanks for the feedback!" : "We'll improve!"
    );
  };

  const formatTime = (value?: string | number) => {
    if (value === undefined || value === null || value === "") return "";

    let date: Date | null = null;
    if (typeof value === "number") {
      const ms = value < 1_000_000_000_000 ? value * 1000 : value;
      date = new Date(ms);
    } else {
      const raw = String(value).trim();
      if (/^\d+$/.test(raw)) {
        const num = Number(raw);
        const ms = num < 1_000_000_000_000 ? num * 1000 : num;
        date = new Date(ms);
      } else {
        const isoLike = raw.includes(" ") && !raw.includes("T")
          ? raw.replace(" ", "T")
          : raw;
        const hasTimezone = /[zZ]|[+\-]\d{2}:\d{2}$/.test(isoLike);
        const normalized = hasTimezone ? isoLike : `${isoLike}Z`;
        date = new Date(normalized);
      }
    }

    if (!date || Number.isNaN(date.getTime())) return "";
    return new Intl.DateTimeFormat(undefined, {
      hour: "numeric",
      minute: "2-digit",
    }).format(date);
  };

  return (
    <div
      className={cn(
        "group w-full flex items-start gap-3 animate-fade-in-up",
        isUser ? "justify-end" : "justify-start"
      )}
      style={{ animationDelay: `${index * 50}ms` }}
    >
      {/* Avatar */}
      <div
        className={cn(
          "w-9 h-9 rounded-full flex items-center justify-center shrink-0 border",
          isUser
            ? "bg-primary text-primary-foreground border-primary/20"
            : "bg-muted text-foreground border-border"
        )}
      >
        {isUser ? (
          <User className="w-4 h-4" />
        ) : (
          <Sparkles className="w-4 h-4 text-muted-foreground" />
        )}
      </div>

      {/* Message */}
      <div
        className={cn(
          "min-w-0",
          isUser ? "max-w-[92%] sm:max-w-[88%]" : "max-w-[94%] sm:max-w-[90%]"
        )}
      >
        <div
          className={cn(
            "rounded-2xl relative px-4 py-3 border shadow-sm overflow-hidden min-w-0",
            isUser
              ? "bg-primary text-primary-foreground border-primary/25"
              : "bg-[hsl(var(--chat-surface)/0.92)] text-foreground border-[hsl(var(--chat-surface-border)/0.9)] shadow-md shadow-black/10 dark:shadow-black/30"
          )}
        >
          {/* Message Rendering */}
          {message.pipeline ? (
            <PlannerStageMessage pipeline={message.pipeline} />
          ) : message.agent === "generator" ? (
            <GeneratorMessage progress={message.generatorProgress} />
          ) : message.agent === "validator" ? (
            <ValidatorMessage passed={message.validationPassed} architectureData={message.architectureData} />
          ) : message.agent === "architect" && message.architectureData ? (
            <ProjectExplanationCard data={message.architectureData} projectTitle={title || undefined} />
          ) : message.agent === "planner" ? (
            <div className="space-y-2 text-sm leading-relaxed">
              {title && (
                <p className={cn("font-semibold", isUser ? "text-primary-foreground" : "text-foreground")}>
                  {renderHighlightedPlain(title, searchHighlight, isUser)}
                </p>
              )}
              {planSteps.map((step, idx) => (
                <div key={idx} className={cn(isUser ? "text-primary-foreground/90" : "text-foreground")}>
                  <ReactMarkdown rehypePlugins={[...searchRehypePlugins]}>
                    {`Step ${idx + 1}: ${step}`}
                  </ReactMarkdown>
                </div>
              ))}
            </div>
          ) : message.agent === "developer" ? (
            <p className={cn("text-sm font-medium leading-relaxed", isUser ? "text-primary-foreground" : "text-foreground")}>
              Code for:{" "}
              {renderHighlightedPlain(title || "your project", searchHighlight, isUser)}
            </p>
          ) : (
            <>
              {isUser && message.attachments && message.attachments.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-2">
                  {message.attachments.map((att) =>
                    att.kind === "image" ? (
                      <a
                        key={att.id}
                        href={att.url}
                        target="_blank"
                        rel="noreferrer"
                        className="relative block overflow-hidden rounded-xl border border-primary-foreground/20 shadow-sm"
                      >
                        <img
                          src={att.url}
                          alt={att.name}
                          className="h-14 w-14 object-cover sm:h-16 sm:w-16"
                        />
                      </a>
                    ) : (
                      <div
                        key={att.id}
                        className={cn(
                          "flex max-w-[220px] items-center gap-2 rounded-xl border px-2.5 py-1.5",
                          "border-primary-foreground/25 bg-primary-foreground/10",
                        )}
                        title={att.name}
                      >
                        <FileText className="h-4 w-4 shrink-0 opacity-90" />
                        <span className="truncate text-xs font-medium text-primary-foreground">
                          {att.name}
                        </span>
                      </div>
                    ),
                  )}
                </div>
              )}
              {message.content.trim().length > 0 && (
                <div className={cn(
                  "text-sm leading-relaxed min-w-0 overflow-hidden",
                  "[&_pre]:overflow-x-auto [&_pre]:max-w-full [&_pre]:rounded-lg [&_pre]:bg-black/40 [&_pre]:p-3 [&_pre]:my-2 [&_pre]:text-xs [&_pre]:font-mono",
                  "[&_code]:break-all [&_pre_code]:break-normal [&_pre_code]:whitespace-pre",
                  "[&_p]:leading-relaxed [&_p]:my-1",
                  "[&_ul]:list-disc [&_ul]:pl-4 [&_ul]:my-1",
                  "[&_ol]:list-decimal [&_ol]:pl-4 [&_ol]:my-1",
                  "[&_h1]:text-base [&_h1]:font-bold [&_h2]:text-sm [&_h2]:font-semibold [&_h3]:text-sm [&_h3]:font-semibold",
                  isUser ? "text-primary-foreground" : "text-foreground",
                )}>
                  <ReactMarkdown rehypePlugins={[...searchRehypePlugins]}>
                    {message.content}
                  </ReactMarkdown>
                </div>
              )}
            </>
          )}

          {/* Code Block */}
          {parsedCode && (
            <CodeBlock
              code={parsedCode.content}
              language={parsedCode.language}
            />
          )}

          {/* Action Buttons */}
          {!isUser && (
            <div className="flex items-center gap-1 mt-3 pt-2 border-t border-border/40 opacity-0 group-hover:opacity-100 transition">
              <button
                onClick={handleCopy}
                className={cn(
                  "flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs",
                  copied
                    ? "bg-emerald-500/10 text-emerald-500"
                    : "text-muted-foreground hover:bg-background/60"
                )}
              >
                {copied ? (
                  <Check className="w-3.5 h-3.5" />
                ) : (
                  <Copy className="w-3.5 h-3.5" />
                )}
                {copied ? "Copied" : "Copy"}
              </button>

              <button className="p-1.5 rounded-lg hover:bg-background/60 text-muted-foreground">
                <RotateCcw className="w-3 h-3" />
              </button>

              <button
                onClick={() => handleFeedback("up")}
                className={cn(
                  "p-1.5 rounded-lg",
                  feedback === "up"
                    ? "bg-emerald-500/10 text-emerald-500"
                    : "text-muted-foreground hover:bg-background/60"
                )}
              >
                <ThumbsUp className="w-3 h-3" />
              </button>

              <button
                onClick={() => handleFeedback("down")}
                className={cn(
                  "p-1.5 rounded-lg",
                  feedback === "down"
                    ? "bg-destructive/10 text-destructive"
                    : "text-muted-foreground hover:bg-background/60"
                )}
              >
                <ThumbsDown className="w-3 h-3" />
              </button>
            </div>
          )}
        </div>

        {/* Timestamp */}
        <div
          className={cn(
            "text-[10px] text-muted-foreground mt-1",
            isUser && "text-right"
          )}
        >
          {formatTime(message.createdAt) || "—"}
        </div>
      </div>
    </div>
  );
}
