import { useState, useRef, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import {
  Plus,
  Mic,
  Send,
  Square,
  FileText,
  Image as ImageIcon,
  X,
} from "lucide-react";
import { toast } from "sonner";

export type ChatAttachmentPayload = {
  name: string;
  mimeType: string;
  kind: "image" | "file";
  dataUrl: string;
  base64: string;
};

interface MessageInputProps {
  onSend: (message: string, attachments?: ChatAttachmentPayload[]) => void;
  isLoading?: boolean;
  /** Assistant is responding (streaming or pipeline) — show Stop instead of Send */
  isGenerating?: boolean;
  onStopGeneration?: () => void;
}

const MAX_FILES = 8;
/** Keep WebSocket JSON payloads reasonable when sending base64 */
const MAX_BYTES = 6 * 1024 * 1024;
const MAX_MB = Math.round(MAX_BYTES / (1024 * 1024));
/** After this much quiet time while dictating, send automatically (ms) */
const VOICE_SILENCE_AUTO_SEND_MS = 1500;

type PendingAttachment = {
  id: string;
  file: File;
  kind: "image" | "file";
  previewUrl?: string;
};

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(new Error("read failed"));
    r.readAsDataURL(file);
  });
}

function dataUrlToBase64(dataUrl: string): string {
  const i = dataUrl.indexOf(",");
  return i >= 0 ? dataUrl.slice(i + 1) : dataUrl;
}

type SpeechRecognitionCtor = new () => SpeechRecognitionInstance;

type SpeechRecognitionInstance = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((ev: SpeechRecognitionResultEvent) => void) | null;
  onerror: ((ev: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
};

type SpeechRecognitionResultEvent = {
  resultIndex: number;
  results: SpeechRecognitionResultList;
};

type SpeechRecognitionResultList = {
  length: number;
  [index: number]: { isFinal: boolean; 0: { transcript: string } };
};

type SpeechRecognitionErrorEvent = {
  error: string;
  message?: string;
};

function getSpeechRecognition(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function MessageInput({
  onSend,
  isLoading = false,
  isGenerating = false,
  onStopGeneration,
}: MessageInputProps) {
  const [message, setMessage] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [attachOpen, setAttachOpen] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(false);
  const [pending, setPending] = useState<PendingAttachment[]>([]);
  const [isPreparingSend, setIsPreparingSend] = useState(false);
  /** Only show vertical scroll when content exceeds max height (avoids empty-state scrollbar). */
  const [textareaNeedsScroll, setTextareaNeedsScroll] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  /** Text before the current dictation segment (typed + prior finalized speech) */
  const voiceBaseRef = useRef("");
  /** Keep mic session alive across Chrome’s auto onend after pauses */
  const keepListeningRef = useRef(false);
  const messageRef = useRef(message);
  messageRef.current = message;
  const isGeneratingRef = useRef(isGenerating);
  isGeneratingRef.current = isGenerating;
  const pendingRef = useRef(pending);
  pendingRef.current = pending;
  const silenceAutoSendTimerRef = useRef<number | null>(null);
  const handleSubmitRef = useRef<() => void>(() => {});

  const clearVoiceSilenceTimer = useCallback(() => {
    if (silenceAutoSendTimerRef.current !== null) {
      window.clearTimeout(silenceAutoSendTimerRef.current);
      silenceAutoSendTimerRef.current = null;
    }
  }, []);

  const TEXTAREA_MAX_PX = 120;

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    const fullScrollHeight = ta.scrollHeight;
    const nextHeight = Math.min(fullScrollHeight, TEXTAREA_MAX_PX);
    ta.style.height = `${nextHeight}px`;
    setTextareaNeedsScroll(fullScrollHeight > TEXTAREA_MAX_PX);
  }, [message]);

  useEffect(() => {
    return () => {
      pendingRef.current.forEach((p) => {
        if (p.previewUrl) URL.revokeObjectURL(p.previewUrl);
      });
    };
  }, []);

  const removePending = useCallback((id: string) => {
    setPending((prev) => {
      const p = prev.find((x) => x.id === id);
      if (p?.previewUrl) URL.revokeObjectURL(p.previewUrl);
      return prev.filter((x) => x.id !== id);
    });
  }, []);

  const addFiles = useCallback(
    (fileList: FileList | null, source: "file" | "image") => {
      if (!fileList?.length) return;

      if (source === "image") {
        if (pendingRef.current.some((p) => p.kind === "file")) {
          toast.error("Remove file attachments before adding images.");
          setAttachOpen(false);
          return;
        }
      } else {
        if (pendingRef.current.some((p) => p.kind === "image")) {
          toast.error("Remove image attachments before adding files.");
          setAttachOpen(false);
          return;
        }
      }

      const additions: PendingAttachment[] = [];
      for (const file of Array.from(fileList)) {
        if (pendingRef.current.length + additions.length >= MAX_FILES) {
          toast.error(`You can attach up to ${MAX_FILES} files.`);
          break;
        }
        if (file.size > MAX_BYTES) {
          toast.error(`"${file.name}" is too large (max ${MAX_MB} MB).`);
          continue;
        }
        if (source === "image" && !file.type.startsWith("image/")) {
          toast.error(`"${file.name}" is not an image.`);
          continue;
        }
        if (source === "file" && file.type.startsWith("image/")) {
          toast.error(
            `"${file.name}" is an image — use Images, or remove files first.`,
          );
          continue;
        }
        const kind: "image" | "file" = source === "image" ? "image" : "file";
        const id = `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
        const previewUrl =
          kind === "image" ? URL.createObjectURL(file) : undefined;
        additions.push({ id, file, kind, previewUrl });
      }
      if (additions.length) setPending((prev) => [...prev, ...additions]);
      setAttachOpen(false);
    },
    [],
  );

  useEffect(() => {
    const Ctor = getSpeechRecognition();
    if (!Ctor) return;

    const recognition = new Ctor();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang =
      typeof navigator !== "undefined" && navigator.language
        ? navigator.language
        : "en-US";
    recognition.maxAlternatives = 1;

    recognition.onresult = (event: SpeechRecognitionResultEvent) => {
      const base = voiceBaseRef.current.trimEnd();
      let segment = "";
      for (let i = 0; i < event.results.length; i++) {
        segment += event.results[i]?.[0]?.transcript ?? "";
      }
      segment = segment.trim();
      const merged = [base, segment].filter(Boolean).join(" ");
      setMessage(merged);
      messageRef.current = merged;

      if (silenceAutoSendTimerRef.current !== null) {
        window.clearTimeout(silenceAutoSendTimerRef.current);
        silenceAutoSendTimerRef.current = null;
      }
      if (keepListeningRef.current) {
        silenceAutoSendTimerRef.current = window.setTimeout(() => {
          silenceAutoSendTimerRef.current = null;
          if (!keepListeningRef.current) return;
          if (isGeneratingRef.current) return;
          const text = messageRef.current.trim();
          const pend = pendingRef.current;
          if (!text && pend.length === 0) return;
          handleSubmitRef.current();
        }, VOICE_SILENCE_AUTO_SEND_MS);
      }
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      const code = event.error;
      if (code === "aborted") return;
      if (code === "no-speech") return;
      if (silenceAutoSendTimerRef.current !== null) {
        window.clearTimeout(silenceAutoSendTimerRef.current);
        silenceAutoSendTimerRef.current = null;
      }
      keepListeningRef.current = false;
      setIsRecording(false);
      if (code === "not-allowed") {
        toast.error("Microphone blocked", {
          description:
            "Allow microphone access in your browser settings to use voice input.",
        });
      } else if (code === "network") {
        toast.error("Voice input needs a network connection", {
          description:
            "Speech recognition uses a cloud service in most browsers.",
        });
      } else {
        toast.error("Voice input error", {
          description: event.message || code,
        });
      }
    };

    recognition.onend = () => {
      if (!keepListeningRef.current) {
        if (silenceAutoSendTimerRef.current !== null) {
          window.clearTimeout(silenceAutoSendTimerRef.current);
          silenceAutoSendTimerRef.current = null;
        }
        setIsRecording(false);
        return;
      }
      voiceBaseRef.current = messageRef.current.trimEnd();
      try {
        recognition.start();
      } catch {
        keepListeningRef.current = false;
        setIsRecording(false);
      }
    };

    recognitionRef.current = recognition;
    setSpeechSupported(true);
    return () => {
      keepListeningRef.current = false;
      if (silenceAutoSendTimerRef.current !== null) {
        window.clearTimeout(silenceAutoSendTimerRef.current);
        silenceAutoSendTimerRef.current = null;
      }
      try {
        recognition.abort();
      } catch {
        try {
          recognition.stop();
        } catch {
          // no-op
        }
      }
      recognitionRef.current = null;
    };
  }, []);

  const stopDictation = useCallback(() => {
    keepListeningRef.current = false;
    if (silenceAutoSendTimerRef.current !== null) {
      window.clearTimeout(silenceAutoSendTimerRef.current);
      silenceAutoSendTimerRef.current = null;
    }
    try {
      recognitionRef.current?.stop();
    } catch {
      // no-op
    }
    setIsRecording(false);
  }, []);

  useEffect(() => {
    if ((isLoading || isGenerating) && isRecording) stopDictation();
  }, [isLoading, isGenerating, isRecording, stopDictation]);

  const handleSubmit = useCallback(async () => {
    const text = messageRef.current.trim();
    const pend = pendingRef.current;
    const canSend =
      (text.length > 0 || pend.length > 0) &&
      !isLoading &&
      !isPreparingSend &&
      !isGenerating;
    if (!canSend) return;

    clearVoiceSilenceTimer();
    stopDictation();
    setIsPreparingSend(true);
    try {
      const payloads: ChatAttachmentPayload[] = [];
      for (const p of pend) {
        const dataUrl = await readFileAsDataUrl(p.file);
        payloads.push({
          name: p.file.name,
          mimeType: p.file.type || "application/octet-stream",
          kind: p.kind,
          dataUrl,
          base64: dataUrlToBase64(dataUrl),
        });
      }

      pend.forEach((p) => {
        if (p.previewUrl) URL.revokeObjectURL(p.previewUrl);
      });
      setPending([]);
      onSend(text, payloads.length ? payloads : undefined);
      setMessage("");
      messageRef.current = "";
      setAttachOpen(false);
    } catch {
      toast.error("Could not read one of the files. Try again.");
    } finally {
      setIsPreparingSend(false);
    }
  }, [
    isLoading,
    isGenerating,
    isPreparingSend,
    onSend,
    stopDictation,
    clearVoiceSilenceTimer,
  ]);

  handleSubmitRef.current = () => {
    void handleSubmit();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      if (isGenerating) return;
      e.preventDefault();
      handleSubmit();
    }
  };

  const toggleRecording = () => {
    if (isLoading || isGenerating) return;
    const recognition = recognitionRef.current;
    if (!recognition) {
      toast.error("Voice input isn’t available in this browser.");
      return;
    }

    setAttachOpen(false);

    if (isRecording) {
      stopDictation();
      return;
    }

    voiceBaseRef.current = messageRef.current.trimEnd();
    keepListeningRef.current = true;
    try {
      recognition.start();
      setIsRecording(true);
    } catch {
      keepListeningRef.current = false;
      setIsRecording(false);
      toast.error("Could not start microphone", {
        description: "Check permissions and try again.",
      });
    }
  };

  const sendDisabled =
    (!message.trim() && pending.length === 0) ||
    isLoading ||
    isPreparingSend ||
    isGenerating;

  const hasAttachments = pending.length > 0;
  const hasImageAttachments = pending.some((p) => p.kind === "image");
  const hasFileAttachments = pending.some((p) => p.kind === "file");

  const handlePickFile = () => {
    if (hasImageAttachments) {
      toast.error("Remove image attachments before adding files.");
      setAttachOpen(false);
      return;
    }
    setAttachOpen(false);
    fileInputRef.current?.click();
  };

  const handlePickImage = () => {
    if (hasFileAttachments) {
      toast.error("Remove file attachments before adding images.");
      setAttachOpen(false);
      return;
    }
    setAttachOpen(false);
    imageInputRef.current?.click();
  };

  return (
    <div className="sticky bottom-0 z-20">
      <div className="pointer-events-none flex justify-center px-3 sm:px-4 md:px-5 pb-4">
        <div className="pointer-events-auto flex w-full max-w-[900px] flex-col gap-2">
          {hasAttachments && (
            <div
              className={cn(
                "self-start max-w-full",
                "inline-flex flex-wrap items-center justify-start gap-1.5 sm:gap-2",
                "rounded-xl sm:rounded-2xl border border-[hsl(var(--chat-surface-border)/0.85)]",
                "bg-[hsl(var(--chat-surface)/0.88)] backdrop-blur-md dark:bg-[hsl(var(--chat-surface)/0.75)]",
                "px-1.5 py-1 sm:px-2 sm:py-1.5",
                "shadow-sm transition-[padding] duration-200",
                pending.length === 1 && "px-1 py-1",
              )}
            >
              {pending.map((a) => (
                <div key={a.id} className="group relative shrink-0">
                  {a.kind === "image" && a.previewUrl ? (
                    <div className="relative h-11 w-11 overflow-hidden rounded-lg border border-border/60 bg-muted/30 sm:h-12 sm:w-12 sm:rounded-xl">
                      <img
                        src={a.previewUrl}
                        alt=""
                        className="h-full w-full object-cover"
                      />
                    </div>
                  ) : (
                    <div
                      className="flex h-11 w-11 flex-col items-center justify-center gap-0.5 rounded-lg border border-border/60 bg-muted/40 px-0.5 sm:h-12 sm:w-12 sm:rounded-xl sm:px-1"
                      title={a.file.name}
                    >
                      <FileText className="h-4 w-4 text-muted-foreground sm:h-5 sm:w-5" />
                      <span className="max-w-[2.75rem] truncate text-[8px] text-muted-foreground sm:max-w-[3.25rem] sm:text-[9px]">
                        {a.file.name?.split(".")?.pop() ?? ""}
                      </span>
                    </div>
                  )}
                  <button
                    type="button"
                    onClick={() => removePending(a.id)}
                    className={cn(
                      "absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full",
                      "border border-border bg-background text-foreground shadow-sm",
                      "opacity-90 transition hover:bg-muted hover:opacity-100",
                    )}
                    aria-label={`Remove ${a.file.name}`}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div
            className={cn(
              "relative flex items-center gap-2 px-2.5 py-2",
              hasAttachments ? "rounded-2xl" : "rounded-full",
              "bg-[hsl(var(--foreground)/0.075)] border-[hsl(var(--foreground)/0.14)] shadow-lg shadow-black/15 ring-1 ring-black/5 dark:bg-[hsl(var(--foreground)/0.09)] dark:ring-white/8 backdrop-blur-md",
              "transition-all duration-200",
              isFocused
                ? "ring-2 ring-primary/25 shadow-md shadow-primary/10"
                : "hover:border-border/90",
            )}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => {
                addFiles(e.target.files, "file");
                e.target.value = "";
              }}
            />
            <input
              ref={imageInputRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={(e) => {
                addFiles(e.target.files, "image");
                e.target.value = "";
              }}
            />

            <div className="relative">
              <button
                type="button"
                onClick={() => setAttachOpen((v) => !v)}
                disabled={isLoading || isPreparingSend || isGenerating}
                className={cn(
                  "inline-flex h-9 w-9 items-center justify-center rounded-full",
                  "text-muted-foreground hover:text-foreground",
                  "hover:bg-background/40 transition-colors",
                )}
                title="Attach"
                aria-label="Attach"
                aria-expanded={attachOpen}
              >
                <Plus className="h-4 w-4" />
              </button>

              {attachOpen && (
                <>
                  <button
                    type="button"
                    className="fixed inset-0 z-10 cursor-default bg-black/20 dark:bg-black/40"
                    aria-label="Close attach menu"
                    onClick={() => setAttachOpen(false)}
                  />
                  <div
                    className={cn(
                      "absolute bottom-full left-0 z-20 mb-2 w-60 overflow-hidden rounded-xl",
                      "border border-border/80 bg-popover text-popover-foreground shadow-xl",
                      "backdrop-blur-md",
                    )}
                  >
                    <p className="border-b border-border/60 px-3 py-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                      Add to message
                    </p>
                    <button
                      type="button"
                      onClick={handlePickFile}
                      className={cn(
                        "flex w-full items-center gap-3 px-3 py-2.5 text-sm transition-colors",
                        hasImageAttachments
                          ? "cursor-not-allowed opacity-45"
                          : "hover:bg-secondary/80",
                      )}
                    >
                      <FileText className="h-4 w-4 shrink-0 text-primary" />
                      <span className="text-left">
                        <span className="block font-medium">Files</span>
                        <span className="text-[11px] text-muted-foreground">
                          {hasImageAttachments
                            ? "Not available with images attached"
                            : `Multiple files (max ${MAX_FILES})`}
                        </span>
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={handlePickImage}
                      className={cn(
                        "flex w-full items-center gap-3 border-t border-border/50 px-3 py-2.5 text-sm transition-colors",
                        hasFileAttachments
                          ? "cursor-not-allowed opacity-45"
                          : "hover:bg-secondary/80",
                      )}
                    >
                      <ImageIcon className="h-4 w-4 shrink-0 text-primary" />
                      <span className="text-left">
                        <span className="block font-medium">Images</span>
                        <span className="text-[11px] text-muted-foreground">
                          {hasFileAttachments
                            ? "Not available with files attached"
                            : "PNG, JPG, GIF, WebP…"}
                        </span>
                      </span>
                    </button>
                  </div>
                </>
              )}
            </div>

            <textarea
              ref={textareaRef}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              placeholder={
                isRecording
                  ? "Listening… speak naturally"
                  : "Ask a question or describe your task…"
              }
              readOnly={isRecording}
              aria-busy={isRecording}
              className={cn(
                "min-h-[40px] w-full flex-1 resize-none bg-transparent",
                "px-2 py-2 text-sm text-foreground placeholder:text-muted-foreground/80",
                "focus:outline-none leading-normal",
                textareaNeedsScroll
                  ? "overflow-y-auto scrollbar-thin"
                  : "overflow-y-hidden scrollbar-none",
                isRecording && "cursor-default text-foreground/95",
              )}
              rows={1}
              disabled={isLoading || isPreparingSend}
            />

            <button
              type="button"
              onClick={toggleRecording}
              disabled={
                isLoading || isPreparingSend || isGenerating || !speechSupported
              }
              className={cn(
                "relative inline-flex h-9 w-9 items-center justify-center rounded-full transition-colors",
                isRecording
                  ? "bg-primary/20 text-primary ring-2 ring-primary/35 shadow-sm shadow-primary/10"
                  : "text-muted-foreground hover:text-foreground hover:bg-background/40",
                !speechSupported && "opacity-50 cursor-not-allowed",
              )}
              title={
                !speechSupported
                  ? "Voice input not supported in this browser"
                  : isRecording
                    ? "Stop dictation"
                    : "Dictate (voice to text)"
              }
              aria-pressed={isRecording}
              aria-label={
                isRecording ? "Stop dictation" : "Start voice dictation"
              }
            >
              <Mic className={cn("h-4 w-4", isRecording && "animate-pulse")} />
            </button>

            {isGenerating ? (
              <button
                type="button"
                onClick={() => onStopGeneration?.()}
                className={cn(
                  "inline-flex h-9 w-9 items-center justify-center rounded-full transition-all",
                  "bg-foreground text-background hover:bg-foreground/90",
                  "shadow-sm ring-1 ring-border/60",
                )}
                title="Stop generating"
                aria-label="Stop generating"
              >
                <Square className="h-3.5 w-3.5 fill-current" strokeWidth={0} />
              </button>
            ) : (
              <button
                type="button"
                onClick={() => void handleSubmit()}
                disabled={sendDisabled}
                className={cn(
                  "inline-flex h-9 w-9 items-center justify-center rounded-full transition-all",
                  !sendDisabled
                    ? "bg-primary text-primary-foreground hover:bg-primary/90"
                    : "bg-background/40 text-muted-foreground",
                )}
                title="Send"
                aria-label="Send"
              >
                <Send className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
