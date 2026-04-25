import {
  useState,
  useRef,
  useEffect,
  useLayoutEffect,
  useCallback,
} from "react";
import { ChatMessage } from "./ChatMessage";
import type { PlannerPipelineState, StageStatus } from "./PlannerStageMessage";
import type { DeveloperPipelineState } from "./DeveloperStageMessage";
import {
  MessageInput,
  type ChatAttachmentPayload,
  type MessageInputMenuAction,
} from "./MessageInput";
import {
  GeneratedAssetsPanel,
  type UmlDiagramAsset,
} from "./GeneratedAssetsPanel";
import type { DebuggerState } from "./ValidatorMessage";
import {
  Sparkles,
  Code,
  FileText,
  User,
  Palette,
  Globe,
  MessageSquare,
  ChevronDown,
} from "lucide-react";
import { cn, isElementNearBottom } from "@/lib/utils";
import { useAuth } from "@/context/AuthContext";
import { useParams, useNavigate } from "react-router-dom";
import { useChatSearch } from "@/context/ChatSearchContext";
import { useAppData } from "@/context/useAppData";
import { API_BASE } from "@/lib/api";
import { toast } from "sonner";

interface MessageAttachmentView {
  id: string;
  name: string;
  kind: "image" | "file";
  mimeType: string;
  url: string;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  title?: string;
  agent?: "developer" | "debugger" | "planner" | "generator" | "validator" | "architect" | "Conversation" | string | null;
  createdAt?: string | number;
  code?: {
    language: string;
    content: string;
  };
  attachments?: MessageAttachmentView[];
  pipeline?: PlannerPipelineState;
  developerPipeline?: DeveloperPipelineState;
  generatorProgress?: { received: number; total: number; done: boolean };
  validationPassed?: boolean | null;
  architectureData?: Record<string, unknown>;
  debuggerState?: DebuggerState;
}

interface Props {
  selectedchatId: string | null;
  onCodeGenerated?: (
    code: string,
    lang: string,
    new_project_id: string,
  ) => void;
  /** After AI edits existing project files (diffs available in app context). */
  onCodeEdited?: (projectId: string) => void;
}

const suggestions = [
  {
    icon: Code,
    label: "Generate code",
    prompt: "Help me create a React component",
  },
  { icon: Palette, label: "Design UI", prompt: "Design a modern landing page" },
  {
    icon: Globe,
    label: "Build app",
    prompt: "Build a full-stack web application",
  },
  {
    icon: MessageSquare,
    label: "Explain concept",
    prompt: "Explain how React hooks work",
  },
];

export function ChatContainer({ onCodeGenerated, onCodeEdited }: Props) {
  const { userId } = useAuth();
  const {
    refreshData,
    mergeCodeDiffs,
    projectFiles,
    setSelectedFile,
    userProjects,
  } = useAppData();
  const { chatId } = useParams();
  const {
    registerMessages,
    registerScrollParent,
    activeMessageId,
    debouncedQuery,
  } = useChatSearch();

  const navigate = useNavigate();
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  /** True from send until assistant finishes, errors, or user stops — drives Stop button in input */
  const [isGenerating, setIsGenerating] = useState(false);
  const [umlDiagrams, setUmlDiagrams] = useState<UmlDiagramAsset[]>([]);
  const [pptUrl, setPptUrl] = useState<string | null>(null);
  const [pptViewerUrl, setPptViewerUrl] = useState<string | null>(null);
  const [isGeneratingUml, setIsGeneratingUml] = useState(false);
  const [isGeneratingPpt, setIsGeneratingPpt] = useState(false);
  const chatWsRef = useRef<WebSocket | null>(null);
  const wsGenerationActiveRef = useRef(false);
  // const [chatId, setchatId] = useState<string | null>(null);
  const [chatHistoryLoading, setChatHistoryLoading] = useState(false);
  const [dateIndicator, setDateIndicator] = useState("");
  const [showDateIndicator, setShowDateIndicator] = useState(false);

  const chatScrollRef = useRef<HTMLDivElement>(null);
  const hideDateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** Active assistant message id while WebSocket is streaming tokens */
  const streamingMessageIdRef = useRef<string | null>(null);
  /** ID of the live planner stage message bubble */
  const plannerMsgIdRef = useRef<string | null>(null);
  /** ID of the live developer progress bubble */
  const developerMsgIdRef = useRef<string | null>(null);
  /** ID of the live validator bubble */
  const validatorMsgIdRef = useRef<string | null>(null);
  /** Accumulated planner_delta text */
  const plannerTextRef = useRef<string>("");
  /** Smooth quick “typing”: split network chunks into small rAF batches */
  const streamCharQueueRef = useRef<string[]>([]);
  const streamRafRef = useRef<number | null>(null);
  /** False after conversation_done/error → blocks stale rAF callbacks from opening a new bubble */
  const streamingActiveRef = useRef(false);
  /** When false, new tokens must not yank scroll (user reading earlier messages) */
  const stickToBottomRef = useRef(true);
  const [showJumpToBottom, setShowJumpToBottom] = useState(false);
  const activeProject =
    userProjects.find((project: any) => project?.chat_id === chatId) ?? null;
  const activeProjectId =
    typeof activeProject?._id === "string" ? activeProject._id : null;

  const loadGeneratedAssets = useCallback(async (projectId: string) => {
    try {
      const res = await fetch(`${API_BASE}/projects/${projectId}/assets`);
      if (!res.ok) return;
      const data = await res.json();
      setUmlDiagrams(Array.isArray(data.diagrams) ? data.diagrams : []);
      setPptUrl(typeof data.ppt_url === "string" ? data.ppt_url : null);
      console.log(data);
      
      setPptViewerUrl(
        typeof data.viewer_url === "string" ? data.viewer_url : null,
      );
    } catch (err) {
      console.error("Failed to load generated assets:", err);
    }
  }, []);

  useLayoutEffect(() => {
    registerScrollParent(chatScrollRef.current);
    return () => registerScrollParent(null);
  }, [registerScrollParent]);

  useEffect(() => {
    if (!activeProjectId) {
      setUmlDiagrams([]);
      setPptUrl(null);
      setPptViewerUrl(null);
      return;
    }
    void loadGeneratedAssets(activeProjectId);
  }, [activeProjectId, loadGeneratedAssets]);

  useEffect(() => {
    registerMessages(
      messages.map((m) => ({ id: m.id, content: m.content ?? "" })),
    );
  }, [messages, registerMessages]);

  const clearTransientStreamingState = useCallback(() => {
    streamingActiveRef.current = false;
    if (streamRafRef.current !== null) {
      cancelAnimationFrame(streamRafRef.current);
      streamRafRef.current = null;
    }
    streamCharQueueRef.current = [];
    streamingMessageIdRef.current = null;
    plannerMsgIdRef.current = null;
    developerMsgIdRef.current = null;
    validatorMsgIdRef.current = null;
    plannerTextRef.current = "";
  }, []);

  const handleStopGeneration = useCallback(() => {
    wsGenerationActiveRef.current = false;
    clearTransientStreamingState();
    const w = chatWsRef.current;
    chatWsRef.current = null;
    if (w) {
      try {
        w.onmessage = null;
        w.onerror = null;
        w.onopen = null;
        w.close();
      } catch {
        // no-op
      }
    }
    setIsGenerating(false);
    setIsLoading(false);
  }, [clearTransientStreamingState]);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    const container = chatScrollRef.current;

    if (container) {
      container.scrollTo({
        top: container.scrollHeight,
        behavior,
      });
    }
  }, []);

  const handleGenerateUml = useCallback(async () => {
    if (!activeProjectId) {
      toast.error("Create or open a project first.");
      return;
    }

    setIsGeneratingUml(true);
    try {
      const res = await fetch(`${API_BASE}/projects/${activeProjectId}/generate-uml`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.detail || "Failed to generate UML diagrams.");
      }
      setUmlDiagrams(Array.isArray(data.diagrams) ? data.diagrams : []);
      toast.success(data.cached ? "Loaded cached UML diagrams." : "UML diagrams generated.");
      scrollToBottom("smooth");
    } catch (err) {
      console.error("Failed to generate UML diagrams:", err);
      toast.error(
        err instanceof Error ? err.message : "Could not generate UML diagrams.",
      );
    } finally {
      setIsGeneratingUml(false);
    }
  }, [activeProjectId, scrollToBottom]);

  const handleGeneratePpt = useCallback(async () => {
    if (!activeProjectId) {
      toast.error("Create or open a project first.");
      return;
    }

    setIsGeneratingPpt(true);
    try {
      const res = await fetch(`${API_BASE}/projects/${activeProjectId}/generate-ppt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.detail || "Failed to generate presentation.");
      }
      await loadGeneratedAssets(activeProjectId);
      toast.success(
        data.cached ? "Loaded cached presentation." : "Presentation generated.",
      );
      scrollToBottom("smooth");
    } catch (err) {
      console.error("Failed to generate presentation:", err);
      toast.error(
        err instanceof Error ? err.message : "Could not generate presentation.",
      );
    } finally {
      setIsGeneratingPpt(false);
    }
  }, [activeProjectId, loadGeneratedAssets, scrollToBottom]);

  useEffect(() => {
    requestAnimationFrame(() => {
      const container = chatScrollRef.current;
      if (!container) return;
      if (stickToBottomRef.current) {
        container.scrollTo({
          top: container.scrollHeight,
          behavior: "auto",
        });
      }
    });
  }, [messages]);

  const parseMessageDate = (raw?: string | number) => {
    if (raw === undefined || raw === null || raw === "") return null;

    if (typeof raw === "number") {
      // Handle unix seconds from backend
      const ms = raw < 1_000_000_000_000 ? raw * 1000 : raw;
      const date = new Date(ms);
      return Number.isNaN(date.getTime()) ? null : date;
    }

    const value = String(raw).trim();

    // Numeric string timestamp support
    if (/^\d+$/.test(value)) {
      const num = Number(value);
      const ms = num < 1_000_000_000_000 ? num * 1000 : num;
      const date = new Date(ms);
      return Number.isNaN(date.getTime()) ? null : date;
    }

    // Backend often returns UTC timestamps without timezone info.
    // Normalize "YYYY-MM-DD HH:mm:ss" -> ISO and force UTC for naive values.
    const isoLike =
      value.includes(" ") && !value.includes("T")
        ? value.replace(" ", "T")
        : value;
    const hasTimezone = /[zZ]|[+\-]\d{2}:\d{2}$/.test(isoLike);
    const normalized = hasTimezone ? isoLike : `${isoLike}Z`;
    const date = new Date(normalized);
    return Number.isNaN(date.getTime()) ? null : date;
  };

  const getDateLabel = (raw?: string | number) => {
    const date = parseMessageDate(raw);
    if (!date) return "";

    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const target = new Date(
      date.getFullYear(),
      date.getMonth(),
      date.getDate(),
    );
    const diffDays = Math.floor(
      (today.getTime() - target.getTime()) / 86400000,
    );

    if (diffDays === 0) return "Today";
    if (diffDays === 1) return "Yesterday";
    return `${date.getDate()}-${date.getMonth() + 1}-${date.getFullYear()}`;
  };

  const showDateChipFor = (text: string) => {
    if (!text) return;
    setDateIndicator(text);
    setShowDateIndicator(true);
    if (hideDateTimerRef.current) clearTimeout(hideDateTimerRef.current);
    hideDateTimerRef.current = setTimeout(() => {
      setShowDateIndicator(false);
    }, 3000);
  };

  const getTopVisibleMessageDateLabel = () => {
    const container = chatScrollRef.current;
    if (!container) return "";

    const containerRect = container.getBoundingClientRect();
    const rows = container.querySelectorAll<HTMLElement>(
      "[data-message-created-at]",
    );
    for (const row of rows) {
      const rowRect = row.getBoundingClientRect();
      if (rowRect.bottom > containerRect.top + 8) {
        const createdAt = row.dataset.messageCreatedAt;
        return getDateLabel(createdAt);
      }
    }
    return "";
  };

  const handleScroll = () => {
    const container = chatScrollRef.current;
    if (container) {
      const near = isElementNearBottom(container);
      stickToBottomRef.current = near;
      const jump = !near && messages.length > 0;
      setShowJumpToBottom((prev) => (prev === jump ? prev : jump));
    }
    const label = getTopVisibleMessageDateLabel();
    if (label) showDateChipFor(label);
  };
  // Load chat history
  useEffect(() => {
    if (!chatId) {
      wsGenerationActiveRef.current = false;
      clearTransientStreamingState();
      if (chatWsRef.current) {
        try {
          chatWsRef.current.close();
        } catch {
          // no-op
        }
        chatWsRef.current = null;
      }
      setMessages([]);
      stickToBottomRef.current = true;
      setShowJumpToBottom(false);
      return;
    }

    const loadChat = async () => {
      try {
        wsGenerationActiveRef.current = false;
        clearTransientStreamingState();
        if (chatWsRef.current) {
          try {
            chatWsRef.current.close();
          } catch {
            // no-op
          }
          chatWsRef.current = null;
        }
        setChatHistoryLoading(true);

        const res = await fetch(`http://localhost:8000/chat/${chatId}`);
        const data = await res.json();

        if (data.ok && Array.isArray(data.messages)) {
          const mapped = data.messages.map((msg: any) => {
            // Parse architectureData from content for stored architect messages
            let architectureData: Record<string, unknown> | undefined;
            let validationPassed: boolean | null | undefined;

            if (msg.agent === "architect" && msg.content) {
              try { architectureData = JSON.parse(msg.content); } catch {}
            }
            if (msg.agent === "validator" || msg.agent === "debugger") {
              validationPassed = msg.validation_passed ?? msg.validationPassed ?? null;
            }

            return {
              id: msg._id,
              role: msg.role,
              content: msg.content,
              createdAt:
                parseMessageDate(
                  msg.created_at ||
                    msg.createdAt ||
                    msg.timestamp ||
                    msg.created ||
                    null,
                )?.toISOString() || null,
              pipeline: msg.pipeline || undefined,
              developerPipeline:
                msg.developer_pipeline || msg.developerPipeline || undefined,
              debuggerState:
                msg.debugger_pipeline || msg.debuggerPipeline || undefined,
              architectureData,
              validationPassed,
              agent: msg.agent === "debugger" ? "validator" : msg.agent,
            };
          });

          setMessages(mapped);
          stickToBottomRef.current = true;
          setShowJumpToBottom(false);
          setChatHistoryLoading(false);
        }
      } catch (err) {
        console.error("Failed to load chat:", err);
        setChatHistoryLoading(false);
      }
    };

    loadChat();
  }, [chatId, clearTransientStreamingState]);

  // Only when the conversation shape changes (not every token during streaming)
  useEffect(() => {
    if (!messages.length) return;
    requestAnimationFrame(() => {
      const label =
        getTopVisibleMessageDateLabel() ||
        getDateLabel(messages[messages.length - 1]?.createdAt);
      if (label) showDateChipFor(label);
    });
  }, [chatId, messages.length]);

  useEffect(() => {
    return () => {
      if (hideDateTimerRef.current) clearTimeout(hideDateTimerRef.current);
    };
  }, []);

  const addMessage = (
    role: "user" | "assistant",
    content: string,
    agent?: string,
  ) => {
    setMessages((prev) => [
      ...prev,
      {
        id: Date.now().toString(),
        role,
        content,
        agent,
        createdAt: new Date().toISOString(),
      },
    ]);
  };

  const appendDeveloperUpdate = (
    updates: string[] | undefined,
    nextUpdate?: string,
  ) => {
    const trimmed = (nextUpdate ?? "").trim();
    if (!trimmed) return updates ?? [];
    const deduped = (updates ?? []).filter((item) => item !== trimmed);
    return [...deduped, trimmed].slice(-6);
  };

  const appendDebuggerUpdate = (
    updates: string[] | undefined,
    nextUpdate?: string,
  ) => {
    const trimmed = (nextUpdate ?? "").trim();
    if (!trimmed) return updates ?? [];
    const deduped = (updates ?? []).filter((item) => item !== trimmed);
    return [...deduped, trimmed].slice(-6);
  };

  const updateDeveloperPipeline = (
    updater: (pipeline: DeveloperPipelineState) => DeveloperPipelineState,
  ) => {
    const targetId = developerMsgIdRef.current;
    if (!targetId) return;
    setMessages((prev) =>
      prev.map((message) =>
        message.id === targetId && message.developerPipeline
          ? {
              ...message,
              developerPipeline: updater(message.developerPipeline),
            }
          : message,
      ),
    );
  };

  const updateDebuggerState = (
    updater: (state: DebuggerState) => DebuggerState,
  ) => {
    const targetId = validatorMsgIdRef.current;
    if (!targetId) return;
    setMessages((prev) =>
      prev.map((message) =>
        message.id === targetId && message.debuggerState
          ? {
              ...message,
              debuggerState: updater(message.debuggerState),
            }
          : message,
      ),
    );
  };

  // Handle send
  const handleSend = async (
    content: string,
    rawAttachments?: ChatAttachmentPayload[],
  ) => {
    if (!content.trim() && !rawAttachments?.length) return;

    const attachmentsView: MessageAttachmentView[] | undefined =
      rawAttachments?.map((a, i) => ({
        id: `att-${Date.now()}-${i}`,
        name: a.name,
        kind: a.kind,
        mimeType: a.mimeType,
        url: a.dataUrl,
      }));

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: content.trim(),
      createdAt: new Date().toISOString(),
      ...(attachmentsView?.length ? { attachments: attachmentsView } : {}),
    };

    stickToBottomRef.current = true;
    setShowJumpToBottom(false);
    setMessages((prev) => [...prev, userMessage]);

    if (chatWsRef.current) {
      try {
        chatWsRef.current.close();
      } catch {
        // no-op
      }
      chatWsRef.current = null;
    }

    setIsGenerating(true);
    setIsLoading(true);
    streamingMessageIdRef.current = null;
    streamCharQueueRef.current = [];
    if (streamRafRef.current !== null) {
      cancelAnimationFrame(streamRafRef.current);
      streamRafRef.current = null;
    }
    streamingActiveRef.current = true;
    wsGenerationActiveRef.current = true;

    const ws = new WebSocket("ws://localhost:8000/chat/ws/chat");
    chatWsRef.current = ws;

    const wsMessage = content.trim()
      ? content.trim()
      : rawAttachments?.length
        ? "User shared attachment(s)."
        : "";

    ws.onopen = () => {
      ws.send(
        JSON.stringify({
          user_id: userId,
          chat_id: chatId || null,
          message: wsMessage,
          attachments:
            rawAttachments?.map((a) => ({
              name: a.name,
              mime_type: a.mimeType,
              data_base64: a.base64,
            })) ?? [],
        }),
      );
    };

    const findLastStreamingConversationId = (prev: Message[]) => {
      for (let i = prev.length - 1; i >= 0; i--) {
        const m = prev[i];
        if (
          m.role === "assistant" &&
          m.agent === "Conversation" &&
          String(m.id).startsWith("stream-")
        ) {
          return m.id;
        }
      }
      return null;
    };

    const appendConversationChunk = (chunk: string) => {
      if (!chunk) return;
      setIsLoading(false);
      setMessages((prev) => {
        let sid = streamingMessageIdRef.current;
        const last = prev[prev.length - 1];
        const lastIsStreamAssistant =
          last?.role === "assistant" &&
          last?.agent === "Conversation" &&
          String(last.id).startsWith("stream-");

        if (!sid && lastIsStreamAssistant) {
          streamingMessageIdRef.current = last.id;
          sid = last.id;
        } else if (!sid && streamingActiveRef.current) {
          const fallback = findLastStreamingConversationId(prev);
          if (fallback) {
            streamingMessageIdRef.current = fallback;
            sid = fallback;
          }
        }

        if (!sid) {
          const newId = `stream-${Date.now()}`;
          streamingMessageIdRef.current = newId;
          return [
            ...prev,
            {
              id: newId,
              role: "assistant" as const,
              content: chunk,
              agent: "Conversation",
              createdAt: new Date().toISOString(),
            },
          ];
        }
        const hasTarget = prev.some((m) => m.id === sid);
        if (
          !hasTarget &&
          (streamingActiveRef.current || lastIsStreamAssistant)
        ) {
          const fallback = lastIsStreamAssistant
            ? last.id
            : findLastStreamingConversationId(prev);
          if (fallback) {
            streamingMessageIdRef.current = fallback;
            sid = fallback;
          }
        }
        return prev.map((m) =>
          m.id === sid ? { ...m, content: m.content + chunk } : m,
        );
      });
    };

    const flushStreamQueue = () => {
      streamRafRef.current = null;
      if (!streamingActiveRef.current) return;
      const charsPerFrame = 2;
      let batch = "";
      for (
        let i = 0;
        i < charsPerFrame && streamCharQueueRef.current.length;
        i++
      ) {
        batch += streamCharQueueRef.current.shift()!;
      }
      if (batch) appendConversationChunk(batch);
      if (streamCharQueueRef.current.length && streamingActiveRef.current) {
        streamRafRef.current = requestAnimationFrame(flushStreamQueue);
      }
    };

    const enqueueStreamText = (text: string) => {
      if (!text) return;
      for (const char of text) {
        streamCharQueueRef.current.push(char);
      }
      if (!streamingActiveRef.current) {
        flushQueueInstant();
        return;
      }
      if (streamRafRef.current === null) {
        streamRafRef.current = requestAnimationFrame(flushStreamQueue);
      }
    };

    const cancelStreamRaf = () => {
      if (streamRafRef.current !== null) {
        cancelAnimationFrame(streamRafRef.current);
        streamRafRef.current = null;
      }
    };

    /** One-shot append (used for late chunks / errors; skips animation) */
    const flushQueueInstant = () => {
      cancelStreamRaf();
      if (streamCharQueueRef.current.length) {
        const rest = streamCharQueueRef.current.join("");
        streamCharQueueRef.current = [];
        appendConversationChunk(rest);
      }
    };

    const clearStreamingRefs = () => {
      streamingMessageIdRef.current = null;
      streamingActiveRef.current = false;
    };

    /** After server sends conversation_done: never dump the whole queue in one React update */
    const endStreamingSessionAnimated = () => {
      cancelStreamRaf();
      if (streamCharQueueRef.current.length === 0) {
        clearStreamingRefs();
        return;
      }
      streamingActiveRef.current = true;
      const charsPerFrameTail = 14;
      const flushTail = () => {
        streamRafRef.current = null;
        if (!streamingActiveRef.current) return;
        let batch = "";
        for (
          let i = 0;
          i < charsPerFrameTail && streamCharQueueRef.current.length;
          i++
        ) {
          batch += streamCharQueueRef.current.shift()!;
        }
        if (batch) appendConversationChunk(batch);
        if (streamCharQueueRef.current.length) {
          streamRafRef.current = requestAnimationFrame(flushTail);
        } else {
          clearStreamingRefs();
        }
      };
      streamRafRef.current = requestAnimationFrame(flushTail);
    };

    const endStreamingSessionImmediate = () => {
      flushQueueInstant();
      clearStreamingRefs();
    };

    ws.onmessage = (event) => {
      if (!wsGenerationActiveRef.current) return;
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (e) {
        console.error("WebSocket JSON parse error:", e);
        // Try to handle as plain text if not JSON
        const text = event.data;
        if (typeof text === "string" && text.length > 0) {
          // Append as raw text conversation chunk
          enqueueStreamText(text);
        }
        return;
      }

      // Streaming conversation (Gemini chunks)
      if (data.type === "conversation_start") {
        if (!streamingMessageIdRef.current) {
          setIsLoading(false);
          const newId = `stream-${Date.now()}`;
          streamingMessageIdRef.current = newId;
          setMessages((prev) => [
            ...prev,
            {
              id: newId,
              role: "assistant",
              content: "",
              agent: "Conversation",
              createdAt: new Date().toISOString(),
            },
          ]);
        }
      }

      if (data.type === "edit_start") {
        setIsLoading(true);
      }

      if (data.type === "edit_file" && data.change) {
        mergeCodeDiffs([data.change]);
        // Auto-select the file that just got edited so the user sees it live
        // (like Claude Code / Cursor). Match on the relative project path.
        const editedPath = (data.change?.file || "").trim();
        if (editedPath) {
          const match = projectFiles.find((f) => f.path === editedPath);
          if (match) setSelectedFile(match);
        }
        setIsLoading(false);
      }

      if (data.type === "edit_done" && data.ok) {
        endStreamingSessionImmediate();
        if (Array.isArray(data.changes) && data.changes.length) {
          mergeCodeDiffs(data.changes);
        }
        refreshData();
        const summary =
          typeof data.summary === "string" && data.summary.trim()
            ? data.summary.trim()
            : "Code updated.";
        addMessage("assistant", summary, "edit");
        const pid = data.project_id;
        if (typeof pid === "string" && pid) {
          onCodeEdited?.(pid);
        }
        setIsLoading(false);
        setIsGenerating(false);
        wsGenerationActiveRef.current = false;
        ws.close();
      }

      if (data.type === "conversation_delta") {
        enqueueStreamText(typeof data.text === "string" ? data.text : "");
      }

      if (data.type === "conversation_done") {
        refreshData();
        endStreamingSessionAnimated();
        setIsLoading(false);

        const currentChatId = window.location.pathname.split("/c/")[1];

        if (currentChatId !== data.chat_id) {
          navigate(`/c/${data.chat_id}`, { replace: true });
        }
      }

      // Legacy: full reply in one frame (non-streaming servers)
      if (data.type === "conversation") {
        const reply = typeof data.reply === "string" ? data.reply : "";
        const sid = streamingMessageIdRef.current;
        if (sid && streamingActiveRef.current) {
          cancelStreamRaf();
          streamCharQueueRef.current = [];
          setMessages((prev) =>
            prev.map((m) => (m.id === sid ? { ...m, content: reply } : m)),
          );
          endStreamingSessionImmediate();
        } else {
          endStreamingSessionImmediate();
          addMessage("assistant", reply, "Conversation");
        }
        setIsLoading(false);
      }

      console.log("WS EVENT:", data);

      // ─── PLANNER PIPELINE EVENTS ────────────────────────────────────────────

      if (data.type === "planner_start") {
        // Create the live planner bubble with an empty pipeline state
        const msgId = `planner-${Date.now()}`;
        plannerMsgIdRef.current = msgId;
        const initialPipeline: PlannerPipelineState = {
          stages: [1,2,3,4,5].map((n) => ({ stage: n, status: "idle" as StageStatus })),
          currentStage: 0,
          isComplete: false,
        };
        setIsLoading(false);
        setMessages((prev) => [
          ...prev,
          {
            id: msgId,
            role: "assistant",
            content: "",
            agent: "planner",
            createdAt: new Date().toISOString(),
            pipeline: initialPipeline,
          },
        ]);
      }

      // Stage start — mark stage as running
      if (data.type === "stage_start" && plannerMsgIdRef.current) {
        const stageNum = data.stage as number;
        const msg = data.message as string;
        setMessages((prev) => prev.map((m) => {
          if (m.id !== plannerMsgIdRef.current || !m.pipeline) return m;
          return {
            ...m,
            pipeline: {
              ...m.pipeline,
              currentStage: stageNum,
              stages: m.pipeline.stages.map((s) =>
                s.stage === stageNum ? { ...s, status: "running" as StageStatus, message: msg } : s
              ),
            },
          };
        }));
      }

      // Stage complete — mark stage as complete and store output
      if (data.type === "stage_complete" && plannerMsgIdRef.current) {
        const stageNum = data.stage as number;
        const output = data.output as Record<string, unknown>;
        setMessages((prev) => prev.map((m) => {
          if (m.id !== plannerMsgIdRef.current || !m.pipeline) return m;
          return {
            ...m,
            pipeline: {
              ...m.pipeline,
              stages: m.pipeline.stages.map((s) =>
                s.stage === stageNum ? { ...s, status: "complete" as StageStatus, output } : s
              ),
            },
          };
        }));
      }

      // Stage retry
      if (data.type === "stage_retry" && plannerMsgIdRef.current) {
        const stageNum = data.stage as number;
        const msg = (data.message as string) || "Retrying…";
        setMessages((prev) => prev.map((m) => {
          if (m.id !== plannerMsgIdRef.current || !m.pipeline) return m;
          return {
            ...m,
            pipeline: {
              ...m.pipeline,
              stages: m.pipeline.stages.map((s) =>
                s.stage === stageNum ? { ...s, status: "retrying" as StageStatus, message: msg } : s
              ),
            },
          };
        }));
      }

      // Stage warning
      if ((data.type === "stage_warning" || data.type === "stage_error") && plannerMsgIdRef.current) {
        const stageNum = data.stage as number;
        const warnings =
          (data.warnings as string[]) ||
          (data.errors as string[]) ||
          ["Warning"];
        setMessages((prev) => prev.map((m) => {
          if (m.id !== plannerMsgIdRef.current || !m.pipeline) return m;
          return {
            ...m,
            pipeline: {
              ...m.pipeline,
              stages: m.pipeline.stages.map((s) =>
                s.stage === stageNum
                  ? { ...s, status: "warning" as StageStatus, warnings, errors: warnings }
                  : s
              ),
            },
          };
        }));
      }

      // Pipeline complete — mark all done
      if (data.type === "pipeline_complete" && plannerMsgIdRef.current) {
        const userPlan = data.user_plan as Record<string, unknown>;
        const developerPlan = data.developer_plan as Record<string, unknown>;
        setMessages((prev) => prev.map((m) => {
          if (m.id !== plannerMsgIdRef.current || !m.pipeline) return m;
          return {
            ...m,
            content: JSON.stringify(userPlan),
            pipeline: {
              ...m.pipeline,
              isComplete: true,
              userPlan,
              developerPlan,
            },
          };
        }));
      }

      // Planner result (legacy / fallback)
      if (data.type === "planner_result" && !plannerMsgIdRef.current) {
        addMessage("assistant", JSON.stringify(data.data, null, 2), "planner");
      }

      // Planner streaming text
      if (data.type === "planner_delta" && plannerMsgIdRef.current) {
        plannerTextRef.current += (data.text as string) || "";
        const txt = plannerTextRef.current;
        setMessages(prev => prev.map(m =>
          m.id === plannerMsgIdRef.current && m.pipeline
            ? { ...m, pipeline: { ...m.pipeline, planText: txt } }
            : m
        ));
      }

      // Planner result (plan steps)
      if (data.type === "planner_result" && plannerMsgIdRef.current) {
        const plan = data.data as { title?: string; steps?: string[] };
        const result = { title: plan?.title || "", steps: plan?.steps || plan?.plan as string[] || [] };
        setMessages(prev => prev.map(m =>
          m.id === plannerMsgIdRef.current && m.pipeline
            ? { ...m, pipeline: { ...m.pipeline, planText: undefined, planResult: result } }
            : m
        ));
        plannerMsgIdRef.current = null;
      }

      // 💻 DEVELOPER START — create generator bubble
      if (data.type === "developer_start") {
        const msgId = `developer-${Date.now()}`;
        developerMsgIdRef.current = msgId;
        const initialDeveloperPipeline: DeveloperPipelineState = {
          stages: [1, 2, 3, 4, 5].map((stage) => ({
            stage,
            status: "idle",
          })),
          currentStage: 0,
          isComplete: false,
          recentUpdates: [],
        };
        setIsLoading(false);
        setMessages((prev) => [
          ...prev,
          {
            id: msgId,
            role: "assistant",
            content: "",
            agent: "developer",
            createdAt: new Date().toISOString(),
            developerPipeline: initialDeveloperPipeline,
          },
        ]);
      }

      // 💻 DEVELOPER RESULT CHUNK — update progress
      if (data.type === "developer_stage_start" && developerMsgIdRef.current) {
        const stageNum = data.stage as number;
        const message = typeof data.message === "string" ? data.message : "";
        updateDeveloperPipeline((pipeline) => ({
          ...pipeline,
          currentStage: stageNum,
          totalTiers: (data.total_tiers as number | undefined) ?? pipeline.totalTiers,
          currentTier: (data.current_tier as number | undefined) ?? pipeline.currentTier,
          totalFiles: (data.total_files as number | undefined) ?? pipeline.totalFiles,
          currentBatchLabel:
            (data.current_batch_label as string | undefined) ??
            pipeline.currentBatchLabel,
          assembledFiles:
            (data.assembled_files as number | undefined) ?? pipeline.assembledFiles,
          isParallel:
            typeof data.is_parallel === "boolean"
              ? (data.is_parallel as boolean)
              : pipeline.isParallel,
          recentUpdates: appendDeveloperUpdate(pipeline.recentUpdates, message),
          stages: pipeline.stages.map((stage) =>
            stage.stage === stageNum
              ? { ...stage, status: "running", message: message || stage.message }
              : stage
          ),
        }));
      }

      if (data.type === "developer_stage_complete" && developerMsgIdRef.current) {
        const stageNum = data.stage as number;
        const message = typeof data.message === "string" ? data.message : "";
        updateDeveloperPipeline((pipeline) => ({
          ...pipeline,
          currentStage: Math.max(pipeline.currentStage, stageNum),
          totalFiles: (data.total_files as number | undefined) ?? pipeline.totalFiles,
          completedFiles:
            (data.completed_files as number | undefined) ?? pipeline.completedFiles,
          recentUpdates: appendDeveloperUpdate(pipeline.recentUpdates, message),
          isComplete: stageNum >= pipeline.stages.length ? true : pipeline.isComplete,
          stages: pipeline.stages.map((stage) =>
            stage.stage === stageNum
              ? { ...stage, status: "complete", message: message || stage.message }
              : stage
          ),
        }));
      }

      if (data.type === "developer_progress" && developerMsgIdRef.current) {
        const message = typeof data.message === "string" ? data.message : "";
        updateDeveloperPipeline((pipeline) => ({
          ...pipeline,
          totalTiers: (data.total_tiers as number | undefined) ?? pipeline.totalTiers,
          currentTier: (data.current_tier as number | undefined) ?? pipeline.currentTier,
          totalFiles: (data.total_files as number | undefined) ?? pipeline.totalFiles,
          completedFiles:
            (data.completed_files as number | undefined) ?? pipeline.completedFiles,
          currentBatchLabel:
            (data.current_batch_label as string | undefined) ??
            pipeline.currentBatchLabel,
          assembledFiles:
            (data.assembled_files as number | undefined) ?? pipeline.assembledFiles,
          isParallel:
            typeof data.is_parallel === "boolean"
              ? (data.is_parallel as boolean)
              : pipeline.isParallel,
          recentUpdates: appendDeveloperUpdate(pipeline.recentUpdates, message),
        }));
      }

      if (data.type === "developer_result_chunk" && developerMsgIdRef.current) {
        const received = (data.chunk_index as number) + 1;
        const total = data.total_chunks as number;
        updateDeveloperPipeline((pipeline) => ({
          ...pipeline,
          currentStage: 5,
          deliveryChunksReceived: received,
          deliveryChunksTotal: total,
          recentUpdates: appendDeveloperUpdate(
            pipeline.recentUpdates,
            `Delivering project payload (${received}/${total} chunks)`,
          ),
          stages: pipeline.stages.map((stage) => {
            if (stage.stage === 4 && stage.status === "running") {
              return { ...stage, status: "complete" };
            }
            if (stage.stage === 5) {
              return {
                ...stage,
                status: "running",
                message: "Packaging project for delivery...",
              };
            }
            return stage;
          }),
        }));
      }

      // 💻 DEVELOPER RESULT DONE — mark complete
      if (data.type === "developer_result_done" && developerMsgIdRef.current) {
        updateDeveloperPipeline((pipeline) => ({
          ...pipeline,
          currentStage: 5,
          isComplete: true,
          deliveryChunksReceived:
            pipeline.deliveryChunksTotal ?? pipeline.deliveryChunksReceived,
          recentUpdates: appendDeveloperUpdate(
            pipeline.recentUpdates,
            "Developer output delivered successfully",
          ),
          stages: pipeline.stages.map((stage) =>
            stage.stage === 5
              ? {
                  ...stage,
                  status: "complete",
                  message: stage.message || "Developer output ready",
                }
              : stage
          ),
        }));
        developerMsgIdRef.current = null;
      }

      // 🧪 DEBUGGER + ARCHITECT START — create validator bubble
      if (data.type === "debugger_start" || data.type === "architect_start") {
        if (!validatorMsgIdRef.current) {
          const msgId = `val-${Date.now()}`;
          validatorMsgIdRef.current = msgId;
          setIsLoading(false);
          setMessages(prev => [...prev, {
            id: msgId,
            role: "assistant",
            content: "",
            agent: "validator",
            createdAt: new Date().toISOString(),
            validationPassed: null,
            debuggerState: {
              status: "running",
              currentStep: "Preparing validation",
              recentUpdates: [],
              filesProcessed: 0,
              filesFixed: 0,
              issuesFound: 0,
              isComplete: false,
            },
          }]);
        }
      }

      if (data.type === "debugger_progress" && validatorMsgIdRef.current) {
        const message = typeof data.message === "string" ? data.message : "";
        updateDebuggerState((state) => ({
          ...state,
          status: "running",
          currentStep: message || state.currentStep,
          filesProcessed:
            (data.files_processed as number | undefined) ?? state.filesProcessed,
          filesFixed:
            (data.files_fixed as number | undefined) ?? state.filesFixed,
          issuesFound:
            (data.issues_found as number | undefined) ?? state.issuesFound,
          recentUpdates: appendDebuggerUpdate(state.recentUpdates, message),
        }));
      }

      // 🧪 ARCHITECT RESULT — show project explanation card
      if (data.type === "architect_result") {
        const arch = data.data as Record<string, unknown>;
        const explainId = `arch-${Date.now()}`;
        setMessages(prev => [...prev, {
          id: explainId,
          role: "assistant",
          content: "",
          agent: "architect",
          createdAt: new Date().toISOString(),
          architectureData: arch,
        }]);
      }

      // 🧪 DEBUGGER RESULT — update validator bubble
      if (data.type === "debugger_result" && validatorMsgIdRef.current) {
        const valid = data.data as boolean;
        const summary = (data.summary as Record<string, unknown> | undefined) || {};
        setMessages(prev => prev.map(m =>
          m.id === validatorMsgIdRef.current
            ? {
                ...m,
                validationPassed: valid,
                debuggerState: {
                  status: valid ? "complete" : "warning",
                  currentStep: valid ? "Validation complete" : "Validation finished with issues",
                  recentUpdates:
                    (summary.recent_updates as string[] | undefined) ||
                    m.debuggerState?.recentUpdates ||
                    [],
                  filesProcessed:
                    (summary.files_processed as number | undefined) ||
                    m.debuggerState?.filesProcessed ||
                    0,
                  filesFixed: m.debuggerState?.filesFixed || 0,
                  issuesFound:
                    (summary.issues_found as number | undefined) ||
                    m.debuggerState?.issuesFound ||
                    0,
                  isComplete: true,
                },
              }
            : m
        ));
        validatorMsgIdRef.current = null;
      }

      // ✅ DONE
      if (data.type === "done") {
        endStreamingSessionImmediate();
        refreshData();
        onCodeGenerated?.(
          JSON.stringify(data.data),
          data.new_project_id,
          "json",
        );
        console.log(`New Project ID: ${data.new_project_id}`);

        setIsLoading(false);
        setIsGenerating(false);
        wsGenerationActiveRef.current = false;
        ws.close();
      }

      // ❌ ERROR
      if (data.type === "error") {
        endStreamingSessionImmediate();
        addMessage("assistant", data.message, "debugger");
        setIsLoading(false);
        setIsGenerating(false);
        wsGenerationActiveRef.current = false;
        ws.close();
      }
    };

    ws.onerror = (err) => {
      wsGenerationActiveRef.current = false;
      if (chatWsRef.current === ws) chatWsRef.current = null;
      if (streamRafRef.current !== null) {
        cancelAnimationFrame(streamRafRef.current);
        streamRafRef.current = null;
      }
      streamCharQueueRef.current = [];
      streamingMessageIdRef.current = null;
      streamingActiveRef.current = false;
      addMessage("assistant", `Something Went Wrong: ${err}`);
      setIsLoading(false);
      setIsGenerating(false);
      console.error("WebSocket error:", err);
    };

    ws.onclose = () => {
      if (chatWsRef.current === ws) chatWsRef.current = null;
      wsGenerationActiveRef.current = false;
      setIsGenerating(false);
      setIsLoading(false);
      console.log("WebSocket closed");
    };
  };

  const messageInputActions: MessageInputMenuAction[] = [
    {
      id: "generate-uml",
      label: "Generate UML Diagrams",
      description: activeProjectId
        ? "Create reusable architecture and workflow diagrams"
        : "Available once this chat has a generated project",
      icon: Code,
      onSelect: () => {
        void handleGenerateUml();
      },
      disabled:
        !activeProjectId || isGeneratingUml || isGeneratingPpt || isGenerating,
    },
    {
      id: "generate-ppt",
      label: "Generate PPT Presentation",
      description: activeProjectId
        ? "Prepare a presentation deck with visual project context"
        : "Available once this chat has a generated project",
      icon: FileText,
      onSelect: () => {
        void handleGeneratePpt();
      },
      disabled:
        !activeProjectId || isGeneratingUml || isGeneratingPpt || isGenerating,
    },
  ];

  const hasMessages = messages.length > 0;

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden relative">
      {/* Background */}
      <div className="absolute inset-0 ambient-bg pointer-events-none" />

      {/* Floating date indicator */}
      <div className="absolute top-3 left-0 right-0 z-20 flex justify-center pointer-events-none">
        <div
          className={cn(
            "px-3 py-1 rounded-full text-xs font-medium",
            "bg-background/85 border border-border/70 backdrop-blur-md text-muted-foreground",
            "transition-all duration-300",
            showDateIndicator
              ? "opacity-100 translate-y-0"
              : "opacity-0 -translate-y-1",
          )}
        >
          {dateIndicator}
        </div>
      </div>

      {/* Messages */}
      <div
        ref={chatScrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto scrollbar-thin px-3 sm:px-4 md:px-5 py-6 pb-28 relative z-10 transition-opacity duration-300"
      >
        {chatHistoryLoading ? (
          <div className="max-w-[900px] mx-auto space-y-5 animate-fade-in-up">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex flex-col gap-6">
                {/* USER MESSAGE SKELETON */}
                <div className="flex gap-4 flex-row-reverse">
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center shrink-0 animate-pulse-soft">
                    <User className="w-5 h-5 text-white" />
                  </div>

                  <div className="rounded-2xl px-5 py-4 bg-primary/10 border border-primary/30 w-full max-w-md">
                    <div className="space-y-2">
                      <div className="h-3 w-full bg-muted rounded animate-pulse" />
                      <div className="h-3 w-4/5 bg-muted rounded animate-pulse" />
                    </div>
                  </div>
                </div>

                {/* ASSISTANT MESSAGE SKELETON */}
                <div className="flex gap-4">
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center shrink-0 animate-pulse-soft">
                    <Sparkles className="w-5 h-5 text-white" />
                  </div>

                  <div className="glass-premium rounded-2xl px-5 py-4 w-full max-w-md">
                    <div className="h-3 w-32 bg-muted rounded mb-3 animate-pulse" />
                    <div className="space-y-2">
                      <div className="h-3 w-full bg-muted rounded animate-pulse" />
                      <div className="h-3 w-4/5 bg-muted rounded animate-pulse" />
                      <div className="h-3 w-2/3 bg-muted rounded animate-pulse" />
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : !hasMessages ? (
          // Welcome screen
          <div className="h-full flex flex-col items-center justify-center max-w-[900px] mx-auto px-4 sm:px-6 animate-fade-in-up">
            <div className="relative mb-10 overflow-hidden">
              <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-primary via-primary to-accent flex items-center justify-center shadow-2xl glow-intense animate-float">
                <Sparkles className="w-10 h-10 text-white" />
              </div>
              <div className="absolute -inset-3 rounded-full bg-gradient-to-r from-primary/20 to-accent/20 blur-2xl -z-10 animate-pulse-soft" />
            </div>

            <h1 className="text-4xl font-bold text-foreground mb-3 text-center">
              Welcome to <span className="text-gradient-animate">CODEXA</span>
            </h1>

            <p className="text-lg text-muted-foreground text-center mb-10 max-w-md">
              Your intelligent assistant for building amazing applications. Ask
              me anything or try one of these suggestions.
            </p>

            <div className="grid grid-cols-2 gap-3 w-full max-w-lg">
              {suggestions.map((item, index) => (
                <button
                  key={index}
                  onClick={() => handleSend(item.prompt)}
                  className={cn(
                    "group flex items-center gap-3 p-4 rounded-2xl",
                    "bg-secondary/50 hover:bg-secondary border border-border/50 hover:border-primary/30",
                    "transition-all duration-300 text-left",
                    "hover:shadow-lg hover:shadow-primary/10 hover:-translate-y-0.5",
                  )}
                  style={{ animationDelay: `${index * 100}ms` }}
                >
                  <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center group-hover:bg-primary/20 transition-colors">
                    <item.icon className="w-5 h-5 text-primary" />
                  </div>
                  <div>
                    <span className="text-sm font-medium text-foreground block">
                      {item.label}
                    </span>
                    <span className="text-xs text-muted-foreground line-clamp-1">
                      {item.prompt}
                    </span>
                  </div>
                </button>
              ))}
            </div>

            <div className="mt-12 flex items-center gap-6 text-xs text-muted-foreground">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                <span>Real-time responses</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                <span>Code generation</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-accent animate-pulse" />
                <span>Multi-modal AI</span>
              </div>
            </div>
          </div>
        ) : (
          // Chat messages
          <div className="max-w-[900px] mx-auto space-y-5">
            {messages.map((msg, index) => (
              <div
                key={msg.id}
                data-chat-message-id={msg.id}
                data-message-created-at={
                  msg.createdAt ? String(msg.createdAt) : ""
                }
                className={cn(
                  "rounded-2xl transition-shadow duration-200",
                  debouncedQuery.trim() &&
                    activeMessageId === msg.id &&
                    "ring-2 ring-primary/40 ring-offset-2 ring-offset-background",
                )}
              >
                <ChatMessage
                  message={msg}
                  index={index}
                  searchHighlight={debouncedQuery}
                />
              </div>
            ))}

            <GeneratedAssetsPanel
              projectTitle={activeProject?.title ?? null}
              umlDiagrams={umlDiagrams}
              pptUrl={pptUrl}
              viewerUrl={pptViewerUrl}
              isGeneratingUml={isGeneratingUml}
              isGeneratingPpt={isGeneratingPpt}
            />

            {isLoading && (
              <div className="flex gap-3 animate-fade-in-up">
                <div className="w-9 h-9 rounded-full bg-muted/70 border border-border flex items-center justify-center shrink-0">
                  <Sparkles className="w-5 h-5 text-white" />
                </div>
                <div className="rounded-2xl bg-muted px-4 py-2.5 flex items-center gap-3 border border-border/60">
                  <div className="flex items-center gap-1">
                    <div
                      className="w-2 h-2 rounded-full bg-primary animate-bounce"
                      style={{ animationDelay: "0ms" }}
                    />
                    <div
                      className="w-2 h-2 rounded-full bg-primary animate-bounce"
                      style={{ animationDelay: "150ms" }}
                    />
                    <div
                      className="w-2 h-2 rounded-full bg-primary animate-bounce"
                      style={{ animationDelay: "300ms" }}
                    />
                  </div>
                  <span className="text-sm text-muted-foreground">
                    CODEXA is thinking...
                  </span>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {showJumpToBottom && hasMessages && (
        <button
          type="button"
          onClick={() => {
            stickToBottomRef.current = true;
            setShowJumpToBottom(false);
            scrollToBottom("smooth");
          }}
          className={cn(
            "absolute z-30 right-4 sm:right-5 md:right-6 bottom-[5.5rem] sm:bottom-24",
            "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium",
            "bg-[hsl(var(--chat-surface)/0.95)] border border-[hsl(var(--chat-surface-border)/0.9)]",
            "shadow-md shadow-black/10 text-foreground",
            "hover:bg-muted/90 transition-colors",
          )}
        >
          <ChevronDown className="w-3.5 h-3.5 opacity-80" />
          Latest
        </button>
      )}

      <MessageInput
        onSend={handleSend}
        isLoading={isLoading}
        isGenerating={isGenerating}
        onStopGeneration={handleStopGeneration}
        extraActions={messageInputActions}
      />
    </div>
  );
}
