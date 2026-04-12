import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type ChatSearchMessage = { id: string; content: string };

export type ChatSearchHit = {
  messageId: string;
  /** Character offset of the match inside the message content */
  offset: number;
  snippet: string;
};

type ChatSearchContextValue = {
  query: string;
  setQuery: (q: string) => void;
  debouncedQuery: string;
  hits: ChatSearchHit[];
  activeHitIndex: number;
  totalHits: number;
  goToNext: () => void;
  goToPrev: () => void;
  goToHit: (index: number) => void;
  registerMessages: (messages: ChatSearchMessage[]) => void;
  registerScrollParent: (el: HTMLElement | null) => void;
  registerSearchInput: (el: HTMLInputElement | null) => void;
  focusSearchInput: () => void;
  activeMessageId: string | null;
  clearSearch: () => void;
};

const ChatSearchContext = createContext<ChatSearchContextValue | null>(null);

function buildSnippet(text: string, matchStart: number, matchLen: number) {
  const pad = 48;
  const start = Math.max(0, matchStart - pad);
  const end = Math.min(text.length, matchStart + matchLen + pad);
  const prefix = start > 0 ? "…" : "";
  const suffix = end < text.length ? "…" : "";
  const raw = text.slice(start, end).replace(/\s+/g, " ").trim();
  return `${prefix}${raw}${suffix}`;
}

export function ChatSearchProvider({ children }: { children: ReactNode }) {
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatSearchMessage[]>([]);
  const [activeHitIndex, setActiveHitIndex] = useState(0);
  const scrollParentRef = useRef<HTMLElement | null>(null);
  const searchInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQuery(query), 220);
    return () => window.clearTimeout(t);
  }, [query]);

  useEffect(() => {
    setActiveHitIndex(0);
  }, [debouncedQuery]);

  const hits = useMemo(() => {
    const q = debouncedQuery.trim();
    if (!q) return [];

    const qLower = q.toLowerCase();
    const out: ChatSearchHit[] = [];

    for (const msg of chatMessages) {
      const text = msg.content ?? "";
      const lower = text.toLowerCase();
      let start = 0;
      while (true) {
        const idx = lower.indexOf(qLower, start);
        if (idx === -1) break;
        out.push({
          messageId: msg.id,
          offset: idx,
          snippet: buildSnippet(text, idx, q.length),
        });
        start = idx + q.length;
      }
    }

    return out;
  }, [debouncedQuery, chatMessages]);

  useEffect(() => {
    if (hits.length === 0) {
      setActiveHitIndex(0);
      return;
    }
    setActiveHitIndex((i) => Math.min(i, hits.length - 1));
  }, [hits.length]);

  const scrollActiveIntoView = useCallback(() => {
    requestAnimationFrame(() => {
      const hit = hits[activeHitIndex];
      if (!hit) return;
      const root = scrollParentRef.current;
      if (!root) return;
      const safeId =
        typeof CSS !== "undefined" && CSS.escape
          ? CSS.escape(hit.messageId)
          : hit.messageId.replace(/"/g, '\\"');
      const el = root.querySelector<HTMLElement>(
        `[data-chat-message-id="${safeId}"]`,
      );
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }, [hits, activeHitIndex]);

  useEffect(() => {
    if (!debouncedQuery.trim() || hits.length === 0) return;
    scrollActiveIntoView();
  }, [activeHitIndex, debouncedQuery, hits.length, scrollActiveIntoView]);

  const goToNext = useCallback(() => {
    if (hits.length === 0) return;
    setActiveHitIndex((i) => (i + 1) % hits.length);
  }, [hits.length]);

  const goToPrev = useCallback(() => {
    if (hits.length === 0) return;
    setActiveHitIndex((i) => (i - 1 + hits.length) % hits.length);
  }, [hits.length]);

  const goToHit = useCallback(
    (index: number) => {
      if (index < 0 || index >= hits.length) return;
      setActiveHitIndex(index);
    },
    [hits.length],
  );

  const registerMessages = useCallback((messages: ChatSearchMessage[]) => {
    setChatMessages(
      messages.map((m) => ({
        id: m.id,
        content: m.content ?? "",
      })),
    );
  }, []);

  const registerScrollParent = useCallback((el: HTMLElement | null) => {
    scrollParentRef.current = el;
  }, []);

  const registerSearchInput = useCallback((el: HTMLInputElement | null) => {
    searchInputRef.current = el;
  }, []);

  const focusSearchInput = useCallback(() => {
    searchInputRef.current?.focus();
    searchInputRef.current?.select();
  }, []);

  const clearSearch = useCallback(() => {
    setQuery("");
    setDebouncedQuery("");
  }, []);

  const activeHit = hits[activeHitIndex];
  const activeMessageId = activeHit?.messageId ?? null;

  const value: ChatSearchContextValue = {
    query,
    setQuery,
    debouncedQuery,
    hits,
    activeHitIndex,
    totalHits: hits.length,
    goToNext,
    goToPrev,
    goToHit,
    registerMessages,
    registerScrollParent,
    registerSearchInput,
    focusSearchInput,
    activeMessageId,
    clearSearch,
  };

  return (
    <ChatSearchContext.Provider value={value}>
      {children}
    </ChatSearchContext.Provider>
  );
}

export function useChatSearch() {
  const ctx = useContext(ChatSearchContext);
  if (!ctx) {
    throw new Error("useChatSearch must be used within ChatSearchProvider");
  }
  return ctx;
}
