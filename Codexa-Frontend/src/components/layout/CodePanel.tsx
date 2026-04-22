import { useState, useMemo, useRef, useEffect } from "react";
import {
  Copy,
  Check,
  X,
  Download,
  Braces,
  FolderTree,
  Folder,
  File as FileIcon,
  Pencil,
  Save,
  ChevronDown,
  Plus,
  Minus,
} from "lucide-react";
import { cn, isElementNearBottom } from "@/lib/utils";
import { toast } from "sonner";
import { Highlight, themes } from "prism-react-renderer";
import Editor, { DiffEditor } from "@monaco-editor/react";
import { useAppData } from "@/context/useAppData";

const jumpToLatestButtonClass = cn(
  "absolute z-20 right-4 bottom-14",
  "flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium",
  "bg-[hsl(var(--chat-surface)/0.95)] border border-[hsl(var(--chat-surface-border)/0.9)]",
  "shadow-md shadow-black/10 text-foreground",
  "hover:bg-muted/90 transition-colors",
);

// Type definitions for common libraries
const TYPE_DEFINITIONS = `
declare module "react" {
  interface ReactElement {}
  interface Component {}
  const useState: any;
  const useEffect: any;
  const useContext: any;
  const useCallback: any;
  const useMemo: any;
  const useReducer: any;
  const useRef: any;
  const useLayoutEffect: any;
  const Fragment: any;
  const StrictMode: any;
}

declare module "react-dom" {
  const createRoot: any;
  const render: any;
}

declare module "react-router-dom" {
  const useNavigate: any;
  const useParams: any;
  const useLocation: any;
  const useSearchParams: any;
  const Link: any;
  const Navigate: any;
  const Outlet: any;
  const BrowserRouter: any;
  const Routes: any;
  const Route: any;
}

declare module "lucide-react" {
  export const Copy: any;
  export const Check: any;
  export const X: any;
  export const Download: any;
  export const Settings2: any;
  export const Braces: any;
  export const FolderTree: any;
  export const Folder: any;
  export const File: any;
  export const Pencil: any;
  export const Save: any;
  export const Plus: any;
  export const Trash2: any;
  export const Edit: any;
  export const AlertCircle: any;
  export const Info: any;
  export const CheckCircle: any;
  [key: string]: any;
}

declare module "sonner" {
  export const toast: {
    success: (message: string) => void;
    error: (message: string) => void;
    loading: (message: string) => void;
    promise: (promise: Promise<any>, options: any) => void;
  };
}

declare module "prism-react-renderer" {
  export const Highlight: any;
  export const themes: any;
}

declare module "@monaco-editor/react" {
  export const default: any;
}

declare module "*.tsx" {
  const content: any;
  export default content;
}

declare module "*.ts" {
  const content: any;
  export default content;
}

declare module "*.jsx" {
  const content: any;
  export default content;
}

declare module "*.js" {
  const content: any;
  export default content;
}

declare module "*.css" {
  const content: any;
  export default content;
}

declare const React: any;
declare const console: any;
declare const fetch: any;
declare const navigator: any;
declare const URL: any;
declare const Blob: any;
declare const URLSearchParams: any;
`;

type CodeThemeSnapshot = {
  isLight: boolean;
  primary: string;
  accent: string;
  background: string;
  card: string;
  secondary: string;
  border: string;
  foreground: string;
  mutedForeground: string;
  destructive: string;
  prismTheme: any;
  monacoThemeName: string;
};

const codeToolbarButtonClass = cn(
  "inline-flex shrink-0 items-center gap-1 rounded-lg border px-2 py-1.5 text-[10px] font-medium transition-all duration-200",
  "border-[hsl(var(--border)/0.7)] bg-[hsl(var(--background)/0.78)] text-[hsl(var(--muted-foreground))]",
  "hover:border-[hsl(var(--primary)/0.28)] hover:bg-[hsl(var(--primary)/0.08)] hover:text-[hsl(var(--foreground))]",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--primary)/0.32)]",
);

const codeTopBarButtonClass = cn(
  "inline-flex items-center justify-center rounded-xl border border-[hsl(var(--border)/0.72)]",
  "bg-[hsl(var(--background)/0.78)] text-[hsl(var(--muted-foreground))]",
  "transition-all duration-200 hover:border-[hsl(var(--primary)/0.28)] hover:bg-[hsl(var(--primary)/0.08)] hover:text-[hsl(var(--foreground))]",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--primary)/0.3)]",
);

const readResolvedTriplet = (
  styles: CSSStyleDeclaration,
  name: string,
  fallback: string,
  fallbackVar?: string,
) => {
  let value = styles.getPropertyValue(name).trim();

  if ((!value || value.includes("var(")) && fallbackVar) {
    const next = styles.getPropertyValue(fallbackVar).trim();
    if (next && !next.includes("var(")) value = next;
  }

  return value || fallback;
};

const parseHslTriplet = (value: string) => {
  const cleaned = value.replace(/,/g, " ").replace(/\//g, " ").trim();
  const parts = cleaned.split(/\s+/).filter(Boolean);

  if (parts.length < 3) return null;

  const h = Number.parseFloat(parts[0]);
  const s = Number.parseFloat(parts[1].replace("%", ""));
  const l = Number.parseFloat(parts[2].replace("%", ""));

  if ([h, s, l].some((part) => Number.isNaN(part))) return null;

  return {
    h: ((h % 360) + 360) % 360,
    s: Math.min(Math.max(s / 100, 0), 1),
    l: Math.min(Math.max(l / 100, 0), 1),
  };
};

const toHexChannel = (value: number) =>
  Math.round(Math.min(Math.max(value, 0), 255))
    .toString(16)
    .padStart(2, "0");

const hslTripletToHex = (value: string, alpha = 1) => {
  const parsed = parseHslTriplet(value);

  if (!parsed) {
    return alpha < 1 ? "#00000000" : "#000000";
  }

  const { h, s, l } = parsed;
  const hue = h / 360;
  let r = l;
  let g = l;
  let b = l;

  if (s !== 0) {
    const hueToRgb = (p: number, q: number, t: number) => {
      let next = t;
      if (next < 0) next += 1;
      if (next > 1) next -= 1;
      if (next < 1 / 6) return p + (q - p) * 6 * next;
      if (next < 1 / 2) return q;
      if (next < 2 / 3) return p + (q - p) * (2 / 3 - next) * 6;
      return p;
    };

    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    r = hueToRgb(p, q, hue + 1 / 3);
    g = hueToRgb(p, q, hue);
    b = hueToRgb(p, q, hue - 1 / 3);
  }

  const hex = `#${toHexChannel(r * 255)}${toHexChannel(g * 255)}${toHexChannel(b * 255)}`;

  if (alpha >= 1) return hex;

  return `${hex}${toHexChannel(alpha * 255)}`;
};

const readCodeThemeSnapshot = (): CodeThemeSnapshot => {
  if (typeof window === "undefined") {
    return {
      isLight: false,
      primary: "187 100% 42%",
      accent: "262 80% 60%",
      background: "222 47% 6%",
      card: "222 47% 8%",
      secondary: "222 30% 14%",
      border: "222 30% 18%",
      foreground: "210 40% 98%",
      mutedForeground: "215 20% 55%",
      destructive: "0 84% 60%",
      prismTheme: themes.nightOwl,
      monacoThemeName: "codexa-dark",
    };
  }

  const root = document.documentElement;
  const styles = getComputedStyle(root);
  const isLight = root.classList.contains("light");
  const primary = readResolvedTriplet(
    styles,
    "--primary",
    isLight ? "187 100% 35%" : "187 100% 42%",
    "--custom-primary",
  );
  const prismThemeMap = themes as Record<string, any>;

  return {
    isLight,
    primary,
    accent: readResolvedTriplet(styles, "--accent", primary),
    background: readResolvedTriplet(
      styles,
      "--background",
      isLight ? "210 40% 98%" : "222 47% 6%",
    ),
    card: readResolvedTriplet(
      styles,
      "--card",
      isLight ? "0 0% 100%" : "222 47% 8%",
    ),
    secondary: readResolvedTriplet(
      styles,
      "--secondary",
      isLight ? "210 40% 96%" : "222 30% 14%",
    ),
    border: readResolvedTriplet(
      styles,
      "--border",
      isLight ? "214 32% 91%" : "222 30% 18%",
    ),
    foreground: readResolvedTriplet(
      styles,
      "--foreground",
      isLight ? "222 47% 11%" : "210 40% 98%",
    ),
    mutedForeground: readResolvedTriplet(
      styles,
      "--muted-foreground",
      isLight ? "215 16% 47%" : "215 20% 55%",
    ),
    destructive: readResolvedTriplet(styles, "--destructive", "0 84% 60%"),
    prismTheme: isLight
      ? prismThemeMap.github ??
        prismThemeMap.duotoneLight ??
        prismThemeMap.nightOwlLight ??
        prismThemeMap.nightOwl
      : prismThemeMap.nightOwl ??
        prismThemeMap.oceanicNext ??
        prismThemeMap.dracula,
    monacoThemeName: isLight ? "codexa-light" : "codexa-dark",
  };
};

/* ----------------------------------------
   Tree Types (STRICT & SAFE)
---------------------------------------- */
type FolderNode = {
  type: "folder";
  children: Record<string, TreeNode>;
};

type FileNode = {
  type: "file";
  file: any;
};

type TreeNode = FolderNode | FileNode;

function CodePanelLoading({ onClose }: { onClose: () => void }) {
  return (
    <div className="h-full flex flex-col bg-card/50 border-l border-border/50 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border/50 flex items-center justify-between bg-secondary/30">
        <div className="flex items-center gap-2">
          <Braces className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold">Code</span>
          <span className="ml-2 text-xs text-muted-foreground">Loading…</span>
        </div>
        <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-secondary">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Toolbar skeleton */}
      <div className="px-4 py-2 border-b border-border/50 flex items-center justify-between bg-background/20">
        <div className="flex items-center gap-2">
          <div className="h-8 w-28 rounded-lg bg-muted/60 animate-pulse" />
          <div className="h-8 w-36 rounded-lg bg-muted/40 animate-pulse" />
        </div>
        <div className="flex items-center gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="h-8 w-8 rounded-lg bg-muted/50 animate-pulse"
              style={{ animationDelay: `${i * 120}ms` }}
            />
          ))}
        </div>
      </div>

      {/* Viewer skeleton */}
      <div className="flex-1 overflow-hidden bg-[#011627] relative">
        <div className="absolute inset-0 opacity-40 animate-shimmer" />
        <div className="p-4 space-y-3">
          <div className="h-4 w-44 rounded bg-slate-700/60 animate-pulse" />
          {Array.from({ length: 14 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3">
              <div className="h-3 w-8 rounded bg-slate-700/50 animate-pulse" />
              <div
                className="h-3 rounded bg-slate-700/50 animate-pulse"
                style={{ width: `${60 + ((i * 13) % 35)}%` }}
              />
            </div>
          ))}
        </div>
      </div>

      {/* Footer skeleton */}
      <div className="px-4 py-2 border-t border-border/50 bg-secondary/30 text-xs text-muted-foreground flex justify-between">
        <div className="h-3 w-12 rounded bg-muted/50 animate-pulse" />
        <div className="h-3 w-20 rounded bg-muted/50 animate-pulse" />
      </div>
    </div>
  );
}

export function CodePanel({
  isOpen,
  onClose,
}: {
  isOpen: boolean;
  onClose: () => void;
}) {
  const {
    projectFiles,
    selectedFile,
    setSelectedFile,
    singleProjectId,
    codeDiffsByPath,
    setCodeDiffForFile,
    recentEditedPaths,
    latestEditedPath,
  } = useAppData();

  const [copied, setCopied] = useState(false);
  const [showFolderView, setShowFolderView] = useState(selectedFile === null);

  // ✅ NEW STATES
  const [isEditing, setIsEditing] = useState(false);
  const [editedContent, setEditedContent] = useState("");
  const [themeNonce, setThemeNonce] = useState(0);

  const codeScrollRef = useRef<HTMLDivElement>(null);
  const monacoRef = useRef<any>(null);
  const stickToBottomRef = useRef(true);
  const [showJumpToBottom, setShowJumpToBottom] = useState(false);
  const codeTheme = useMemo(() => readCodeThemeSnapshot(), [themeNonce]);

  const activeFile = selectedFile;
  const activeDiff = activeFile
    ? codeDiffsByPath[activeFile.path] ?? null
    : null;

  const applyMonacoTheme = (monaco: any) => {
    monacoRef.current = monaco;
    monaco.editor.defineTheme(codeTheme.monacoThemeName, {
      base: codeTheme.isLight ? "vs" : "vs-dark",
      inherit: true,
      rules: [
        {
          token: "comment",
          foreground: hslTripletToHex(codeTheme.mutedForeground).replace("#", ""),
          fontStyle: "italic",
        },
        {
          token: "keyword",
          foreground: hslTripletToHex(codeTheme.primary).replace("#", ""),
        },
        {
          token: "string",
          foreground: hslTripletToHex(codeTheme.accent).replace("#", ""),
        },
        {
          token: "number",
          foreground: hslTripletToHex(codeTheme.primary).replace("#", ""),
        },
        {
          token: "type.identifier",
          foreground: hslTripletToHex(codeTheme.foreground).replace("#", ""),
        },
      ],
      colors: {
        "editor.background": hslTripletToHex(
          codeTheme.background,
          codeTheme.isLight ? 0.9 : 0.94,
        ),
        "editor.foreground": hslTripletToHex(codeTheme.foreground),
        "editorLineNumber.foreground": hslTripletToHex(
          codeTheme.mutedForeground,
          codeTheme.isLight ? 0.72 : 0.84,
        ),
        "editorLineNumber.activeForeground": hslTripletToHex(
          codeTheme.foreground,
          0.96,
        ),
        "editorCursor.foreground": hslTripletToHex(codeTheme.primary),
        "editor.selectionBackground": hslTripletToHex(
          codeTheme.primary,
          codeTheme.isLight ? 0.18 : 0.2,
        ),
        "editor.inactiveSelectionBackground": hslTripletToHex(
          codeTheme.primary,
          codeTheme.isLight ? 0.1 : 0.12,
        ),
        "editor.lineHighlightBackground": hslTripletToHex(
          codeTheme.primary,
          codeTheme.isLight ? 0.06 : 0.09,
        ),
        "editor.lineHighlightBorder": hslTripletToHex(
          codeTheme.primary,
          codeTheme.isLight ? 0.12 : 0.16,
        ),
        "editorGutter.background": hslTripletToHex(
          codeTheme.background,
          codeTheme.isLight ? 0.82 : 0.92,
        ),
        "editorIndentGuide.background1": hslTripletToHex(
          codeTheme.border,
          codeTheme.isLight ? 0.4 : 0.5,
        ),
        "editorIndentGuide.activeBackground1": hslTripletToHex(
          codeTheme.primary,
          codeTheme.isLight ? 0.32 : 0.4,
        ),
        "editorWhitespace.foreground": hslTripletToHex(
          codeTheme.border,
          codeTheme.isLight ? 0.4 : 0.5,
        ),
        "editorBracketMatch.border": hslTripletToHex(
          codeTheme.accent,
          codeTheme.isLight ? 0.38 : 0.45,
        ),
        "editorBracketMatch.background": hslTripletToHex(
          codeTheme.accent,
          codeTheme.isLight ? 0.08 : 0.12,
        ),
        "editorWidget.background": hslTripletToHex(
          codeTheme.card,
          codeTheme.isLight ? 0.98 : 0.96,
        ),
        "editorWidget.border": hslTripletToHex(
          codeTheme.border,
          codeTheme.isLight ? 0.68 : 0.78,
        ),
        "editorHoverWidget.background": hslTripletToHex(codeTheme.card, 0.98),
        "editorHoverWidget.border": hslTripletToHex(
          codeTheme.border,
          codeTheme.isLight ? 0.68 : 0.78,
        ),
        "editorSuggestWidget.background": hslTripletToHex(codeTheme.card, 0.98),
        "editorSuggestWidget.border": hslTripletToHex(
          codeTheme.border,
          codeTheme.isLight ? 0.68 : 0.78,
        ),
        "editorSuggestWidget.selectedBackground": hslTripletToHex(
          codeTheme.primary,
          codeTheme.isLight ? 0.1 : 0.14,
        ),
        "diffEditor.insertedTextBackground": hslTripletToHex(
          "142 72% 45%",
          codeTheme.isLight ? 0.12 : 0.18,
        ),
        "diffEditor.removedTextBackground": hslTripletToHex(
          codeTheme.destructive,
          codeTheme.isLight ? 0.1 : 0.16,
        ),
      },
    });
    monaco.editor.setTheme(codeTheme.monacoThemeName);
  };

  // Diff stats (lines added / removed) — computed cheaply from before/after.
  const diffStats = useMemo(() => {
    if (!activeDiff) return { added: 0, removed: 0 };
    const beforeLines = (activeDiff.before ?? "").split("\n");
    const afterLines = (activeDiff.after ?? "").split("\n");
    const beforeSet = new Set(beforeLines);
    const afterSet = new Set(afterLines);
    let added = 0;
    let removed = 0;
    for (const l of afterLines) if (!beforeSet.has(l)) added++;
    for (const l of beforeLines) if (!afterSet.has(l)) removed++;
    return { added, removed };
  }, [activeDiff]);

  // "Fresh" diff = arrived in the last ~4 seconds. Drives the entry animation.
  const [freshNonce, setFreshNonce] = useState(0);
  const isFresh = useMemo(() => {
    if (!activeDiff?.receivedAt) return false;
    return Date.now() - activeDiff.receivedAt < 4000;
  }, [activeDiff?.receivedAt, freshNonce]);

  // Force a re-render ~4s after a fresh diff arrives so the "editing" chrome fades.
  useEffect(() => {
    if (!activeDiff?.receivedAt) return;
    const remaining = 4000 - (Date.now() - activeDiff.receivedAt);
    if (remaining <= 0) return;
    const t = setTimeout(() => setFreshNonce((n) => n + 1), remaining + 50);
    return () => clearTimeout(t);
  }, [activeDiff?.receivedAt]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const root = document.documentElement;
    const syncTheme = () => setThemeNonce((nonce) => nonce + 1);
    const observer = new MutationObserver(syncTheme);

    observer.observe(root, {
      attributes: true,
      attributeFilter: ["class", "style"],
    });

    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!monacoRef.current) return;
    applyMonacoTheme(monacoRef.current);
  }, [codeTheme]);

  // When a brand-new edit arrives for a file we aren't currently viewing,
  // jump to it — same feel as Claude Code's live cursor follow.
  useEffect(() => {
    if (!latestEditedPath) return;
    if (activeFile?.path === latestEditedPath) return;
    const target = projectFiles.find((f) => f.path === latestEditedPath);
    if (target) {
      setSelectedFile(target);
      setShowFolderView(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestEditedPath]);

  const scrollCodeToBottom = (behavior: ScrollBehavior = "smooth") => {
    const el = codeScrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior });
  };

  const handleCodeScroll = () => {
    const el = codeScrollRef.current;
    if (!el) return;
    const near = isElementNearBottom(el);
    stickToBottomRef.current = near;
    const hasOverflow = el.scrollHeight > el.clientHeight + 4;
    const jump = !near && hasOverflow;
    setShowJumpToBottom((p) => (p === jump ? p : jump));
  };

  useEffect(() => {
    stickToBottomRef.current = true;
    setShowJumpToBottom(false);
    requestAnimationFrame(() => {
      const el = codeScrollRef.current;
      if (!el) return;
      el.scrollTo({ top: el.scrollHeight, behavior: "auto" });
    });
  }, [activeFile?._id, showFolderView]);

  useEffect(() => {
    if (isEditing) return;
    requestAnimationFrame(() => {
      const el = codeScrollRef.current;
      if (!el) return;
      if (stickToBottomRef.current) {
        el.scrollTo({ top: el.scrollHeight, behavior: "auto" });
      }
    });
  }, [activeFile?.content, isEditing, showFolderView, projectFiles]);
  
  /* ----------------------------------------
     Actions
  ---------------------------------------- */
  const handleCopy = () => {
    if (!activeFile) return;
    navigator.clipboard.writeText(activeFile.content);
    setCopied(true);
    toast.success("Code copied to clipboard!");
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    if (!activeFile) return;
    const blob = new Blob([activeFile.content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = activeFile.name;
    a.click();
    URL.revokeObjectURL(url);
  };
  
  // ✅ SAVE FUNCTION
  const handleSave = async () => {
  if (!activeFile) return;

  try {
    const res = await fetch(
      `http://localhost:8000/files/${activeFile._id}/file`,
      {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          file_id: activeFile._id,
          project_id: singleProjectId,
          path: activeFile.path,
          content: editedContent,
        }),
      }
    );

    const data = await res.json();

    if (data.ok) {
      toast.success("File saved!");

      // ✅ Update UI instantly
      setSelectedFile({
        ...activeFile,
        content: editedContent,
      });

      setIsEditing(false);
    }
  } catch (err) {
    toast.error("Save failed");
  }
};
  const getLanguage = (lang: string) => {
    const map: any = {
      tsx: "typescript",
      ts: "typescript",
      js: "javascript",
      py: "python",
      html: "html",
      css: "css",
      json: "json",
    };
    return map[lang] || "javascript";
  };

  /* ----------------------------------------
     Build Folder Tree
  ---------------------------------------- */
  const folderTree = useMemo<FolderNode>(() => {
    const root: FolderNode = {
      type: "folder",
      children: {},
    };

    projectFiles.forEach((file) => {
      const parts = (file.path ?? "").split("/").filter(Boolean);
      if (!parts.length) return;
      let current: FolderNode = root;

      parts.forEach((part, index) => {
        if (index === parts.length - 1) {
          current.children[part] = {
            type: "file",
            file,
          };
        } else {
          if (!current.children[part]) {
            current.children[part] = {
              type: "folder",
              children: {},
            };
          }
          current = current.children[part] as FolderNode;
        }
      });
    });

    return root;
  }, [projectFiles]);

  /* ----------------------------------------
     Render Tree
  ---------------------------------------- */
  const renderTree = (node: FolderNode, depth = 0) => {
    return Object.entries(node.children)
      .sort(([nameA, a], [nameB, b]) => {
        if (a.type !== b.type) return a.type === "folder" ? -1 : 1;
        return nameA.localeCompare(nameB);
      })
      .map(([name, child]) => {
      const isFile = child.type === "file";
      const isSelected = isFile && activeFile?.path === child.file.path;

      return (
        <div
          key={isFile ? child.file.path : `${depth}-${name}`}
          className="relative"
          style={{ paddingLeft: depth * 14 }}
        >
          <div
            onClick={() => {
              if (child.type === "file") {
                setSelectedFile(child.file);
                setShowFolderView(false);
                setIsEditing(false);
              }
            }}
            className={cn(
              "group/tree relative flex h-8 items-center gap-2 rounded-lg border border-transparent px-2 text-[12px] transition-all duration-150",
              isSelected
                ? "border-[hsl(var(--primary)/0.36)] bg-[linear-gradient(90deg,hsl(var(--primary)/0.2),hsl(var(--primary)/0.08))] text-[hsl(var(--foreground))] shadow-[inset_2px_0_0_hsl(var(--primary))]"
                : "text-[hsl(var(--foreground)/0.84)] hover:border-[hsl(var(--border)/0.72)] hover:bg-[hsl(var(--foreground)/0.065)] hover:text-[hsl(var(--foreground))]",
              isFile ? "cursor-pointer" : "cursor-default",
            )}
          >
            {depth > 0 && (
              <>
                <span className="absolute bottom-1 left-[-7px] top-[-9px] w-[1.5px] bg-[linear-gradient(180deg,hsl(var(--primary)/0.42),hsl(var(--foreground)/0.24))]" />
                <span className="absolute left-[-7px] top-1/2 h-[1.5px] w-[7px] -translate-y-1/2 bg-[hsl(var(--primary)/0.38)]" />
              </>
            )}
            <span
              className={cn(
                "flex h-5 w-5 shrink-0 items-center justify-center rounded-md transition-all duration-150",
                isSelected
                  ? "bg-[hsl(var(--primary)/0.16)] text-[hsl(var(--primary))]"
                  : child.type === "folder"
                    ? "text-[hsl(var(--primary))]"
                    : "text-[hsl(var(--foreground)/0.74)] group-hover/tree:text-[hsl(var(--foreground))]",
              )}
            >
              {child.type === "folder" ? (
                <Folder className="h-3.5 w-3.5" />
              ) : (
                <FileIcon className="h-3.5 w-3.5" />
              )}
            </span>

            <div className="flex min-w-0 flex-1 items-center gap-2">
              <span
                className={cn(
                  "truncate",
                  child.type === "folder"
                    ? "font-semibold text-[hsl(var(--foreground)/0.95)]"
                    : "font-medium text-[hsl(var(--foreground)/0.86)]",
                  isSelected && "text-[hsl(var(--foreground))]",
                )}
              >
                {name}
              </span>
              <span className="ml-auto shrink-0 rounded-full border border-[hsl(var(--border)/0.6)] bg-[hsl(var(--background)/0.5)] px-1.5 py-0.5 text-[9px] uppercase tracking-[0.12em] text-[hsl(var(--foreground)/0.6)]">
                {child.type === "folder" ? Object.keys(child.children).length : child.file.language}
              </span>
            </div>
          </div>

          {child.type === "folder" && (
            <div className="relative py-0.5">
              {renderTree(child, depth + 1)}
            </div>
          )}
        </div>
      );
    });
  };

  if (!isOpen) return <CodePanelLoading onClose={onClose} />;

  return (
    <div className="relative flex h-full flex-col overflow-hidden border-l border-[hsl(var(--border)/0.72)] bg-[linear-gradient(180deg,hsl(var(--card)/0.94),hsl(var(--background)/0.98))] text-foreground">
      {/* Header */}
      <div className="border-b border-[hsl(var(--border)/0.68)] bg-[hsl(var(--background)/0.5)] backdrop-blur-xl">
        <div className="flex items-center justify-between gap-2 px-3 py-1.5">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="relative flex h-7 w-7 items-center justify-center rounded-lg border border-[hsl(var(--primary)/0.18)] bg-[linear-gradient(135deg,hsl(var(--primary)/0.22),hsl(var(--accent)/0.1))] shadow-[0_8px_18px_hsl(var(--primary)/0.12)]">
            <Braces className="h-3.5 w-3.5 text-[hsl(var(--foreground))]" />
            {isFresh && (
              <span className="absolute -top-0.5 -right-0.5 flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
              </span>
            )}
          </div>
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-1.5 overflow-hidden">
              <span className="shrink-0 text-[13px] font-semibold tracking-tight">Code Workspace</span>
              <span className="rounded-full border border-[hsl(var(--primary)/0.2)] bg-[hsl(var(--primary)/0.1)] px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.16em] text-[hsl(var(--primary))]">
                {activeDiff ? "Diff Mode" : isEditing ? "Editing" : "Read Only"}
              </span>
              <span className="rounded-full border border-[hsl(var(--border)/0.62)] bg-[hsl(var(--background)/0.72)] px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
                {projectFiles.length} files
              </span>
            </div>

          </div>

          {activeDiff && (
            <div className="hidden items-center gap-2 rounded-full border border-[hsl(var(--border)/0.62)] bg-[hsl(var(--background)/0.72)] px-3 py-1 text-[11px] font-medium md:flex">
              <span className="flex items-center gap-1 text-emerald-500">
                <Plus className="h-3 w-3" />
                {diffStats.added}
              </span>
              <span className="flex items-center gap-1 text-rose-500">
                <Minus className="h-3 w-3" />
                {diffStats.removed}
              </span>
            </div>
          )}
        </div>
        <button
          onClick={onClose}
          className={cn(codeTopBarButtonClass, "h-7 w-7 shrink-0")}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      </div>

      {/* Recent Changes strip — only when there are live diffs */}
      {recentEditedPaths.length > 0 && (
        <div className="border-b border-[hsl(var(--border)/0.6)] bg-[hsl(var(--background)/0.34)] px-4 py-2.5">
          <div className="flex items-center gap-2 overflow-x-auto scrollbar-none">
            <span className="shrink-0 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Recent edits
            </span>
          <div className="flex items-center gap-1.5">
            {recentEditedPaths.slice(0, 8).map((path) => {
              const fileObj = projectFiles.find((f) => f.path === path);
              const name = fileObj?.name ?? path.split("/").pop() ?? path;
              const isActive = activeFile?.path === path;
              const diff = codeDiffsByPath[path];
              const fresh = diff?.receivedAt && Date.now() - diff.receivedAt < 4000;
              return (
                <button
                  key={path}
                  type="button"
                  onClick={() => {
                    if (fileObj) {
                      setSelectedFile(fileObj);
                      setShowFolderView(false);
                      setIsEditing(false);
                    }
                  }}
                  title={path}
                  className={cn(
                    "shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-all duration-200",
                    isActive
                      ? "border-[hsl(var(--primary)/0.28)] bg-[hsl(var(--primary)/0.12)] text-[hsl(var(--primary))]"
                      : "border-[hsl(var(--border)/0.62)] bg-[hsl(var(--background)/0.7)] text-muted-foreground hover:border-[hsl(var(--primary)/0.18)] hover:bg-[hsl(var(--foreground)/0.05)] hover:text-foreground",
                    fresh && "ring-1 ring-emerald-500/35",
                  )}
                >
                  <span className="flex items-center gap-1.5">
                    <FileIcon className="h-3 w-3" />
                    {name}
                  </span>
                </button>
              );
            })}
          </div>
          </div>
        </div>
      )}

      {/* Toolbar */}
      <div className="border-b border-[hsl(var(--border)/0.6)] bg-[hsl(var(--background)/0.34)] px-2.5 py-1.5">
        <div className="flex min-w-0 items-center justify-between gap-2">
            <button
              onClick={() => setShowFolderView((v) => !v)}
              className={codeToolbarButtonClass}
            >
              <FolderTree className="h-3.5 w-3.5" />
              {showFolderView ? "Show Code" : "Show Files"}
            </button>

          {activeFile && (
            <div className="flex min-w-0 shrink-0 items-center gap-1">
              {activeDiff && (
                <button
                  type="button"
                  onClick={() => setCodeDiffForFile(activeFile.path, null)}
                  className={cn(
                    codeToolbarButtonClass,
                    "border-amber-500/35 text-amber-600 hover:bg-amber-500/10 hover:text-amber-700 dark:text-amber-400 dark:hover:text-amber-300",
                  )}
                  title="Hide diff overlay"
                >
                  Exit diff
                </button>
              )}

              <button
                onClick={() => {
                  setIsEditing(true);
                  setEditedContent(activeFile.content);
                }}
                className={cn(
                  codeToolbarButtonClass,
                  activeDiff && "cursor-not-allowed opacity-50 hover:bg-[hsl(var(--background)/0.78)] hover:text-[hsl(var(--muted-foreground))]",
                )}
                disabled={!!activeDiff}
                title="Edit file"
              >
                <Pencil className="h-3.5 w-3.5" />
                <span>Edit</span>
              </button>

              {isEditing && (
                <button
                  onClick={handleSave}
                  className={cn(
                    codeToolbarButtonClass,
                    "border-[hsl(var(--primary)/0.28)] bg-[linear-gradient(135deg,hsl(var(--primary)/0.16),hsl(var(--accent)/0.08))] text-[hsl(var(--foreground))]",
                  )}
                >
                  <Save className="h-3.5 w-3.5" />
                  <span>Save</span>
                </button>
              )}

              <button
                onClick={handleCopy}
                className={cn(
                  codeToolbarButtonClass,
                  copied && "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
                )}
                title="Copy code"
              >
                {copied ? (
                  <Check className="h-3.5 w-3.5" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
                <span>{copied ? "Copied" : "Copy"}</span>
              </button>

              <button
                onClick={handleDownload}
                className={codeToolbarButtonClass}
                title="Download file"
              >
                <Download className="h-3.5 w-3.5" />
                <span>Download</span>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Viewer */}
      <div className="relative flex-1 min-h-0 p-2.5">
        <div className="code-panel-surface relative h-full overflow-hidden rounded-[24px] border border-[hsl(var(--border)/0.62)] shadow-[0_24px_52px_hsl(var(--background)/0.18)]">
          <div className="code-panel-grid absolute inset-0 opacity-[0.14]" />
          <div className="pointer-events-none absolute inset-x-0 top-0 z-[1] h-24 bg-[linear-gradient(180deg,hsl(var(--primary)/0.12),transparent)] opacity-70" />

          <div
            ref={codeScrollRef}
            onScroll={handleCodeScroll}
            className="code-panel-scrollbar relative z-10 h-full overflow-auto"
          >
            {showFolderView || !activeFile ? (
              <div className="min-h-full p-3">
                <div className="mb-3 flex items-center justify-between gap-3 rounded-2xl border border-[hsl(var(--border)/0.5)] bg-[hsl(var(--background)/0.42)] px-3 py-2">
                  <div className="flex min-w-0 items-center gap-2 text-[hsl(var(--foreground))]">
                    <FolderTree className="h-4 w-4 shrink-0 text-[hsl(var(--primary))]" />
                    <div>
                      <div className="text-xs font-semibold">Project Explorer</div>
                      <div className="truncate text-[10px] text-muted-foreground">
                        Folders and files are grouped like a code workspace.
                      </div>
                    </div>
                  </div>

                  <span className="shrink-0 rounded-full border border-[hsl(var(--border)/0.62)] bg-[hsl(var(--background)/0.72)] px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                    {projectFiles.length} files
                  </span>
                </div>

                <div className="rounded-2xl border border-[hsl(var(--border)/0.64)] bg-[hsl(var(--background)/0.4)] p-1.5 shadow-[inset_0_1px_0_hsl(var(--foreground)/0.05)]">
                  {renderTree(folderTree)}
                </div>
              </div>
            ) : activeDiff ? (
              <div
                key={activeDiff.receivedAt ?? activeDiff.file}
                className={cn(
                  "relative h-full w-full animate-in fade-in-0 zoom-in-[0.98] duration-500",
                  isFresh && "ring-1 ring-inset ring-emerald-500/20",
                )}
              >
                {isFresh && (
                  <div
                    className="pointer-events-none absolute inset-0 z-10 animate-shimmer"
                    style={{
                      background:
                        "linear-gradient(90deg, transparent 0%, rgba(16,185,129,0.12) 50%, transparent 100%)",
                      backgroundSize: "200% 100%",
                    }}
                  />
                )}

                <div className="absolute inset-x-0 top-0 z-20 flex items-center justify-between border-b border-[hsl(var(--border)/0.58)] bg-[hsl(var(--background)/0.7)] px-4 py-2.5 backdrop-blur-xl">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="rounded-full border border-[hsl(var(--primary)/0.2)] bg-[hsl(var(--primary)/0.1)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-[hsl(var(--primary))]">
                      Diff
                    </span>
                    <span className="truncate text-xs text-muted-foreground">
                      {activeFile.path}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-[11px] font-medium">
                    <span className="flex items-center gap-1 text-emerald-500">
                      <Plus className="h-3 w-3" />
                      {diffStats.added}
                    </span>
                    <span className="flex items-center gap-1 text-rose-500">
                      <Minus className="h-3 w-3" />
                      {diffStats.removed}
                    </span>
                  </div>
                </div>

                <div className="absolute inset-x-0 bottom-0 top-[45px]">
                  <DiffEditor
                    beforeMount={applyMonacoTheme}
                    height="100%"
                    theme={codeTheme.monacoThemeName}
                    original={activeDiff.before}
                    modified={activeDiff.after}
                    language={getLanguage(activeFile?.language || "tsx")}
                    options={{
                      readOnly: true,
                      renderSideBySide: true,
                      minimap: { enabled: false },
                      fontSize: 13,
                      fontFamily: "JetBrains Mono, monospace",
                      scrollBeyondLastLine: false,
                      renderOverviewRuler: true,
                      diffWordWrap: "on",
                      automaticLayout: true,
                      renderIndicators: true,
                      smoothScrolling: true,
                      scrollbar: {
                        verticalScrollbarSize: 12,
                        horizontalScrollbarSize: 12,
                        useShadows: false,
                      },
                    }}
                  />
                </div>
              </div>
            ) : isEditing ? (
              <Editor
                beforeMount={applyMonacoTheme}
                height="100%"
                defaultLanguage={getLanguage(activeFile?.language)}
                value={editedContent}
                onChange={(value) => setEditedContent(value || "")}
                theme={codeTheme.monacoThemeName}
                onMount={(editor, monaco) => {
                  applyMonacoTheme(monaco);
                  monaco.languages.typescript.typescriptDefaults.addExtraLib(
                    TYPE_DEFINITIONS,
                    "file:///node_modules/@types/ambient.d.ts"
                  );

                  monaco.languages.typescript.typescriptDefaults.setCompilerOptions({
                    target: monaco.languages.typescript.ScriptTarget.Latest,
                    module: monaco.languages.typescript.ModuleKind.ESNext,
                    lib: ["ES2020", "DOM", "DOM.Iterable"],
                    jsx: monaco.languages.typescript.JsxEmit.React,
                    jsxFactory: "React.createElement",
                    jsxFragmentFactory: "React.Fragment",
                    allowJs: true,
                    strict: false,
                    esModuleInterop: true,
                    skipLibCheck: true,
                    forceConsistentCasingInFileNames: true,
                    resolveJsonModule: true,
                    moduleResolution: monaco.languages.typescript.ModuleResolutionKind.NodeJs,
                  });

                  setTimeout(() => {
                    editor.getAction("editor.action.formatDocument")?.run();
                  }, 200);
                }}
                options={{
                  fontSize: 13,
                  fontFamily: "JetBrains Mono, monospace",
                  minimap: { enabled: false },
                  wordWrap: "on",
                  automaticLayout: true,
                  scrollBeyondLastLine: false,
                  formatOnType: true,
                  formatOnPaste: true,
                  smoothScrolling: true,
                  cursorSmoothCaretAnimation: "on",
                  renderLineHighlight: "all",
                  padding: { top: 18, bottom: 24 },
                  scrollbar: {
                    verticalScrollbarSize: 12,
                    horizontalScrollbarSize: 12,
                    useShadows: false,
                  },
                }}
              />
            ) : (
              <Highlight
                theme={codeTheme.prismTheme}
                code={activeFile.content}
                language={activeFile.language}
              >
                {({ tokens, getLineProps, getTokenProps }) => (
                  <pre className="min-h-full min-w-fit px-4 py-5 text-[13px] leading-6 font-mono text-[hsl(var(--foreground))]">
                    {tokens.map((line, i) => {
                      const lineProps = getLineProps({ line });

                      return (
                        <div
                          key={i}
                          {...lineProps}
                          className={cn(
                            "group flex min-w-fit items-start rounded-xl border-l border-transparent px-2 py-[1px] transition-colors duration-150 hover:border-[hsl(var(--primary)/0.28)] hover:bg-[hsl(var(--primary)/0.08)]",
                            lineProps.className,
                          )}
                        >
                          <span className="w-10 shrink-0 select-none pr-4 text-right text-[11px] font-medium text-[hsl(var(--muted-foreground)/0.82)]">
                            {i + 1}
                          </span>
                          <span className="flex-1 whitespace-pre">
                            {line.map((token, key) => (
                              <span key={key} {...getTokenProps({ token })} />
                            ))}
                          </span>
                        </div>
                      );
                    })}
                  </pre>
                )}
              </Highlight>
            )}
          </div>
        </div>
      </div>

      {showJumpToBottom && !isEditing && (
        <button
          type="button"
          onClick={() => {
            stickToBottomRef.current = true;
            setShowJumpToBottom(false);
            scrollCodeToBottom("smooth");
          }}
          className={jumpToLatestButtonClass}
        >
          <ChevronDown className="w-3.5 h-3.5 opacity-80" />
          Latest
        </button>
      )}

      {/* Footer */}
      {activeFile && (
        <div className="border-t border-[hsl(var(--border)/0.6)] bg-[hsl(var(--background)/0.5)] px-4 py-2 backdrop-blur-xl">
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-[hsl(var(--border)/0.62)] bg-[hsl(var(--background)/0.72)] px-2.5 py-1 font-medium text-foreground">
                {(activeFile.language || "text").toUpperCase()}
              </span>
              <span className="rounded-full border border-[hsl(var(--border)/0.62)] bg-[hsl(var(--background)/0.72)] px-2.5 py-1">
                {(activeFile.content ?? "").split("\n").length} lines
              </span>
            {activeDiff ? (
              <span className="rounded-full border border-[hsl(var(--destructive)/0.18)] bg-[hsl(var(--destructive)/0.08)] px-2.5 py-1 text-[hsl(var(--destructive))]">
                Diff view: red removed, green added
              </span>
            ) : null}
            </div>
            <span className="max-w-full truncate text-[11px]">
              {activeFile.path}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
