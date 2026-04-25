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
import { DeveloperStageMessage } from "./DeveloperStageMessage";
import type { DeveloperPipelineState } from "./DeveloperStageMessage";
import { GeneratorMessage } from "./GeneratorMessage";
import type { GeneratorProgress } from "./GeneratorMessage";
import { ValidatorMessage } from "./ValidatorMessage";
import type { DebuggerState } from "./ValidatorMessage";
import { ProjectExplanationCard } from "./ProjectExplanationCard";
import {
  GeneratedAssetsPanel,
  type UmlDiagramAsset,
} from "./GeneratedAssetsPanel";

interface ChatMessageProps {
  message: {
    id: string;
    role: "user" | "assistant";
    title?: string;
    projectId?: string | null;
    agent:
      | "developer"
      | "debugger"
      | "planner"
      | "generator"
      | "validator"
      | "architect"
      | "chat"
      | string
      | null;
    content: string;
    createdAt?: string | number;
    pipeline?: PlannerPipelineState;
    developerPipeline?: DeveloperPipelineState;
    generatorProgress?: GeneratorProgress;
    validationPassed?: boolean | null;
    architectureData?: Record<string, unknown>;
    debuggerState?: DebuggerState;
    assetPanel?: {
      projectTitle?: string | null;
      umlDiagrams: UmlDiagramAsset[];
      pptUrl?: string | null;
      viewerUrl?: string | null;
      isGeneratingUml?: boolean;
      isGeneratingPpt?: boolean;
    };
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
  onPreviewCode?: () => void;
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

type StructuredConversationBlock =
  | { type: "text"; value: string }
  | { type: "code"; content: string; language: string };

type StructuredMessagePayload =
  | { type: "conversation"; content: StructuredConversationBlock[] }
  | {
      type: "small_project";
      files: Array<{ filename: string; content: string }>;
    };

function normalizeSmallProjectFiles(
  files: unknown,
): Array<{ filename: string; content: string }> {
  if (!Array.isArray(files)) {
    return [];
  }

  return files
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const file = item as Record<string, unknown>;
      const filename =
        typeof file.filename === "string" && file.filename.trim()
          ? file.filename.trim()
          : "index.html";
      const content = extractSmallProjectHtmlContent(file.content) ?? "";
      return content ? { filename, content } : null;
    })
    .filter(
      (item): item is { filename: string; content: string } => item !== null,
    );
}

function deriveSmallProjectFromConversationBlocks(
  blocks: StructuredConversationBlock[],
): Extract<StructuredMessagePayload, { type: "small_project" }> | null {
  const textBlocks = blocks.filter(
    (block): block is Extract<StructuredConversationBlock, { type: "text" }> =>
      block.type === "text" && block.value.trim().length > 0,
  );
  if (textBlocks.length > 1) {
    return null;
  }

  for (const block of blocks) {
    if (block.type !== "code") continue;
    const nested = parseStructuredMessage(block.content);
    if (nested?.type === "small_project" && nested.files.length > 0) {
      return nested;
    }
  }

  return null;
}


function looksLikeHtmlDocument(raw: string) {
  const trimmed = raw.trim().toLowerCase();
  return (
    trimmed.startsWith("<!doctype html") ||
    trimmed.startsWith("<html") ||
    (trimmed.includes("<html") &&
      trimmed.includes("<style") &&
      trimmed.includes("<script"))
  );
}

function extractSmallProjectHtmlContent(value: unknown): string | null {
  let current: unknown = value;

  for (let depth = 0; depth < 6; depth += 1) {
    if (typeof current === "string") {
      const candidate = current.trim();
      if (!candidate) {
        return null;
      }
      if (looksLikeHtmlDocument(candidate)) {
        return candidate.replace(/\s+$/, "");
      }
      if (
        !candidate.startsWith("{") &&
        !candidate.startsWith("[") &&
        !candidate.startsWith('"')
      ) {
        return null;
      }
      try {
        current = JSON.parse(candidate) as unknown;
        continue;
      } catch {
        return null;
      }
    }

    if (Array.isArray(current)) {
      current = current.find(Boolean) ?? null;
      continue;
    }

    if (current && typeof current === "object") {
      const record = current as {
        type?: unknown;
        files?: unknown;
        content?: unknown;
      };
      const type =
        typeof record.type === "string" ? record.type.trim().toLowerCase() : "";

      if (type === "small_project" && Array.isArray(record.files)) {
        const firstFile = record.files.find(
          (item): item is { content?: unknown } =>
            Boolean(item) && typeof item === "object",
        );
        current = firstFile?.content ?? null;
        continue;
      }

      if (type === "conversation" && Array.isArray(record.content)) {
        for (const block of record.content) {
          if (!block || typeof block !== "object") continue;
          const nestedRecord = block as Record<string, unknown>;
          const nestedHtml =
            extractSmallProjectHtmlContent(nestedRecord.content) ??
            extractSmallProjectHtmlContent(nestedRecord.value);
          if (nestedHtml) {
            return nestedHtml;
          }
        }
        return null;
      }

      if ("content" in record) {
        current = record.content;
        continue;
      }
    }

    return null;
  }

  return null;
}

function parseSmallProjectJsonish(
  raw: string,
): { filename: string; content: string } | null {
  if (!/"type"\s*:\s*"small_project"/i.test(raw)) {
    return null;
  }

  const contentMatch = raw.match(/"content"\s*:\s*("(?:\\.|[^"\\])*")/s);
  if (!contentMatch) {
    return null;
  }

  try {
    const rawFilenameMatch = raw.match(
      /"filename"\s*:\s*("(?:\\.|[^"\\])*")/s,
    );
    const filename = rawFilenameMatch
      ? String(JSON.parse(rawFilenameMatch[1]) || "index.html").trim() ||
        "index.html"
      : "index.html";
    const decodedContent = String(JSON.parse(contentMatch[1]) || "");
    const content = extractSmallProjectHtmlContent(decodedContent);
    return content ? { filename, content } : null;
  } catch {
    return null;
  }
}

function parseStructuredMessage(raw: string): StructuredMessagePayload | null {
  let trimmed = raw.trim();
  if (looksLikeHtmlDocument(trimmed)) {
    return {
      type: "small_project",
      files: [{ filename: "index.html", content: raw.replace(/\s+$/, "") }],
    };
  }

  for (let depth = 0; depth < 5; depth += 1) {
    if (!trimmed.startsWith("{") && !trimmed.startsWith('"')) break;

    try {
      const reparsed = JSON.parse(trimmed) as unknown;
      if (typeof reparsed === "string") {
        trimmed = reparsed.trim();
        if (looksLikeHtmlDocument(trimmed)) {
          return {
            type: "small_project",
            files: [
              { filename: "index.html", content: trimmed.replace(/\s+$/, "") },
            ],
          };
        }
        continue;
      }

      if (!reparsed || typeof reparsed !== "object") return null;

      const parsed = reparsed as Record<string, unknown>;
      const type =
        typeof parsed.type === "string" ? parsed.type.trim().toLowerCase() : "";

      if (type === "conversation" && Array.isArray(parsed.content)) {
        const content = parsed.content
          .map((item) => {
            if (!item || typeof item !== "object") return null;
            const block = item as Record<string, unknown>;
            const blockType =
              typeof block.type === "string"
                ? block.type.trim().toLowerCase()
                : "";

            if (blockType === "text") {
              const value =
                typeof block.value === "string" ? block.value.trim() : "";
              return value ? ({ type: "text", value } as const) : null;
            }

            if (blockType === "code") {
              const content =
                typeof block.content === "string"
                  ? block.content.replace(/\s+$/, "")
                  : "";
              const language =
                typeof block.language === "string" && block.language.trim()
                  ? block.language.trim()
                  : "text";
              return content
                ? ({ type: "code", content, language } as const)
                : null;
            }

            return null;
          })
          .filter((item): item is StructuredConversationBlock => item !== null);

        if (!content.length) {
          return null;
        }

        const promotedSmallProject =
          deriveSmallProjectFromConversationBlocks(content);
        if (promotedSmallProject) {
          return promotedSmallProject;
        }

        return { type: "conversation", content };
      }

      if (type === "small_project" && Array.isArray(parsed.files)) {
        const files = normalizeSmallProjectFiles(parsed.files);

        return files.length ? { type: "small_project", files } : null;
      }

      return null;
    } catch {
      const recovered = parseSmallProjectJsonish(trimmed);
      if (recovered) {
        return { type: "small_project", files: [recovered] };
      }
      return null;
    }
  }

  const recovered = parseSmallProjectJsonish(trimmed);
  if (recovered) {
    return { type: "small_project", files: [recovered] };
  }

  return null;
}

export function ChatMessage({
  message,
  index,
  searchHighlight,
  onPreviewCode,
}: ChatMessageProps) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);
  const [planSteps, setPlanSteps] = useState<string[]>([]);
  const [title, setTitle] = useState<string | null>(null);
  const [parsedCode, setParsedCode] = useState(message.code || null);
  const structuredPayload = useMemo(
    () => parseStructuredMessage(message.content),
    [message.content],
  );

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
      const t = (d.project_name ||
        d.title ||
        d.name ||
        message.title ||
        null) as string | null;
      setTitle(t);
    }

    if (
      message.agent === "developer" &&
      structuredPayload?.type !== "small_project"
    ) {
      try {
        const formatted = formatCodeString(message.content, "html");
        setParsedCode(formatted.content.trim().length > 0 ? formatted : null);
      } catch {
        console.error("Developer code formatting failed.");
      }
      return;
    }
    setParsedCode(null);
  }, [message, structuredPayload?.type]);

  const searchRehypePlugins = useMemo(() => {
    const q = searchHighlight?.trim();
    if (!q) return [];
    return [
      [
        rehypeSearchHighlight,
        { query: searchHighlight ?? "", variant: isUser ? "user" : "default" },
      ],
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
      type === "up" ? "Thanks for the feedback!" : "We'll improve!",
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
        const isoLike =
          raw.includes(" ") && !raw.includes("T") ? raw.replace(" ", "T") : raw;
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
        isUser ? "justify-end" : "justify-start",
      )}
      style={{ animationDelay: `${index * 50}ms` }}
    >
      {/* Avatar */}
      <div
        className={cn(
          "w-9 h-9 rounded-full flex items-center justify-center shrink-0 border",
          isUser
            ? "bg-primary text-primary-foreground border-primary/20"
            : "bg-muted text-foreground border-border",
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
          isUser ? "max-w-[92%] sm:max-w-[88%]" : "max-w-[94%] sm:max-w-[90%]",
        )}
      >
        <div
          className={cn(
            "rounded-2xl relative px-4 py-3 border shadow-sm overflow-hidden min-w-0",
            isUser
              ? "bg-primary text-primary-foreground border-primary/25"
              : "bg-[hsl(var(--chat-surface)/0.92)] text-foreground border-[hsl(var(--chat-surface-border)/0.9)] shadow-md shadow-black/10 dark:shadow-black/30",
          )}
        >
          {/* Message Rendering */}
          {message.pipeline ? (
            <PlannerStageMessage pipeline={message.pipeline} />
          ) : message.developerPipeline ? (
            <DeveloperStageMessage pipeline={message.developerPipeline} />
          ) : message.agent === "generator" ? (
            <GeneratorMessage progress={message.generatorProgress} />
          ) : message.agent === "validator" ? (
            <ValidatorMessage
              passed={message.validationPassed}
              architectureData={message.architectureData}
              debuggerState={message.debuggerState}
            />
          ) : message.agent === "architect" && message.architectureData ? (
            <ProjectExplanationCard
              data={message.architectureData}
              projectTitle={title || undefined}
            />
          ) : message.agent === "assets" && message.assetPanel ? (
            <GeneratedAssetsPanel
              projectTitle={message.assetPanel.projectTitle}
              umlDiagrams={message.assetPanel.umlDiagrams}
              pptUrl={message.assetPanel.pptUrl}
              viewerUrl={message.assetPanel.viewerUrl}
              isGeneratingUml={message.assetPanel.isGeneratingUml}
              isGeneratingPpt={message.assetPanel.isGeneratingPpt}
            />
          ) : message.agent === "planner" ? (
            <div className="space-y-2 text-sm leading-relaxed">
              {title && (
                <p
                  className={cn(
                    "font-semibold",
                    isUser ? "text-primary-foreground" : "text-foreground",
                  )}
                >
                  {renderHighlightedPlain(title, searchHighlight, isUser)}
                </p>
              )}
              {planSteps.map((step, idx) => (
                <div
                  key={idx}
                  className={cn(
                    isUser ? "text-primary-foreground/90" : "text-foreground",
                  )}
                >
                  <ReactMarkdown rehypePlugins={[...searchRehypePlugins]}>
                    {`Step ${idx + 1}: ${step}`}
                  </ReactMarkdown>
                </div>
              ))}
            </div>
          ) : structuredPayload?.type === "small_project" ? (
            <div className="space-y-3">
              <div
                className={cn(
                  "rounded-2xl border px-4 py-3 backdrop-blur-xl",
                  isUser
                    ? "border-primary-foreground/20 bg-primary-foreground/10 text-primary-foreground"
                    : "border-border/60 bg-background/40 text-foreground",
                )}
              >
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary/80">
                  Small Project
                </p>
                <p className="mt-2 text-sm font-medium">
                  Single-file app ready for preview
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Inline HTML, CSS, and JavaScript with a complete responsive
                  UI.
                </p>
              </div>

              {structuredPayload.files.map((file) => (
                <div
                  key={file.filename}
                  className={cn(
                    "rounded-2xl border p-3 backdrop-blur-xl",
                    isUser
                      ? "border-primary-foreground/20 bg-primary-foreground/10"
                      : "border-border/60 bg-background/35",
                  )}
                >
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <span className="text-xs font-semibold uppercase tracking-[0.16em] text-primary/80">
                      {file.filename}
                    </span>
                    <span className="text-[11px] text-muted-foreground">
                      Full HTML document
                    </span>
                  </div>
                  <CodeBlock
                    code={file.content}
                    language="html"
                    livePreviewHtml={file.content}
                    livePreviewLabel="Live"
                  />
                </div>
              ))}
            </div>
          ) : structuredPayload?.type === "conversation" ? (
            <div className="space-y-3 text-sm leading-relaxed">
              {structuredPayload.content.map((block, blockIndex) =>
                block.type === "text" ? (
                  <div
                    key={`text-${blockIndex}`}
                    className={cn(
                      "min-w-0 overflow-hidden",
                      "[&_p]:leading-relaxed [&_p]:my-1",
                      "[&_ul]:list-disc [&_ul]:pl-4 [&_ul]:my-1",
                      "[&_ol]:list-decimal [&_ol]:pl-4 [&_ol]:my-1",
                      "[&_h1]:text-base [&_h1]:font-bold [&_h2]:text-sm [&_h2]:font-semibold [&_h3]:text-sm [&_h3]:font-semibold",
                      isUser ? "text-primary-foreground" : "text-foreground",
                    )}
                  >
                    <ReactMarkdown rehypePlugins={[...searchRehypePlugins]}>
                      {block.value}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <CodeBlock
                    key={`code-${blockIndex}`}
                    code={block.content}
                    language={block.language}
                  />
                ),
              )}
            </div>
          ) : message.agent === "developer" ? (
            <p
              className={cn(
                "text-sm font-medium leading-relaxed",
                isUser ? "text-primary-foreground" : "text-foreground",
              )}
            >
              Code for:{" "}
              {renderHighlightedPlain(
                title || "your project",
                searchHighlight,
                isUser,
              )}
            </p>
          ) : (
            <>
              {isUser &&
                message.attachments &&
                message.attachments.length > 0 && (
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
                <div
                  className={cn(
                    "text-sm leading-relaxed min-w-0 overflow-hidden",
                    "[&_pre]:overflow-x-auto [&_pre]:max-w-full [&_pre]:rounded-lg [&_pre]:bg-black/40 [&_pre]:p-3 [&_pre]:my-2 [&_pre]:text-xs [&_pre]:font-mono",
                    "[&_code]:break-all [&_pre_code]:break-normal [&_pre_code]:whitespace-pre",
                    "[&_p]:leading-relaxed [&_p]:my-1",
                    "[&_ul]:list-disc [&_ul]:pl-4 [&_ul]:my-1",
                    "[&_ol]:list-decimal [&_ol]:pl-4 [&_ol]:my-1",
                    "[&_h1]:text-base [&_h1]:font-bold [&_h2]:text-sm [&_h2]:font-semibold [&_h3]:text-sm [&_h3]:font-semibold",
                    isUser ? "text-primary-foreground" : "text-foreground",
                  )}
                >
                  <ReactMarkdown rehypePlugins={[...searchRehypePlugins]}>
                    {message.content}
                  </ReactMarkdown>
                </div>
              )}
            </>
          )}

          {/* Code Block */}
          {parsedCode && !structuredPayload && (
            <CodeBlock
              code={parsedCode.content}
              language={parsedCode.language}
            />
          )}

          {/* Action Buttons */}
          {!isUser && !message.assetPanel && (
            <div className="flex items-center gap-1 mt-3 pt-2 border-t border-border/40 opacity-0 group-hover:opacity-100 transition">
              <button
                onClick={handleCopy}
                className={cn(
                  "flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs",
                  copied
                    ? "bg-emerald-500/10 text-emerald-500"
                    : "text-muted-foreground hover:bg-background/60",
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
                    : "text-muted-foreground hover:bg-background/60",
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
                    : "text-muted-foreground hover:bg-background/60",
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
            isUser && "text-right",
          )}
        >
          {formatTime(message.createdAt) || "—"}
        </div>
      </div>
    </div>
  );
}
