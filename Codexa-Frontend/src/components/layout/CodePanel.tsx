import { useState, useMemo, useRef, useEffect } from "react";
import {
  Copy,
  Check,
  X,
  Download,
  Settings2,
  Braces,
  FolderTree,
  Folder,
  File as FileIcon,
  Pencil,
  Save,
  ChevronDown,
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
  } = useAppData();

  const [copied, setCopied] = useState(false);
  const [showFolderView, setShowFolderView] = useState(selectedFile === null);

  // ✅ NEW STATES
  const [isEditing, setIsEditing] = useState(false);
  const [editedContent, setEditedContent] = useState("");

  const codeScrollRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const [showJumpToBottom, setShowJumpToBottom] = useState(false);

  const activeFile = selectedFile;
  const activeDiff = activeFile
    ? codeDiffsByPath[activeFile.path] ?? null
    : null;

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
  console.log(singleProjectId, activeFile?._id || "");
  
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
      const parts = file.path.split("/");
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
    return Object.entries(node.children).map(([name, child]) => (
      <div key={name} style={{ paddingLeft: depth * 14 }}>
        <div
          onClick={() => {
            if (child.type === "file") {
              setSelectedFile(child.file);
              setShowFolderView(false);
              setIsEditing(false); // reset edit mode
            }
          }}
          className="flex items-center gap-2 py-1 text-sm rounded-md cursor-pointer
                     text-muted-foreground hover:text-foreground
                     hover:bg-secondary/40 transition"
        >
          {child.type === "folder" ? (
            <Folder className="w-4 h-4 text-primary" />
          ) : (
            <FileIcon className="w-4 h-4 text-muted-foreground" />
          )}
          <span className="font-medium">{name}</span>
        </div>

        {child.type === "folder" && renderTree(child, depth + 1)}
      </div>
    ));
  };

  if (!isOpen) return <CodePanelLoading onClose={onClose} />;

  return (
    <div className="relative h-full flex flex-col bg-card/50 border-l border-border/50 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border/50 flex justify-between bg-secondary/30">
        <div className="flex items-center gap-2">
          <Braces className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold">Code</span>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg hover:bg-secondary"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Toolbar */}
      <div className="px-4 py-2 border-b border-border/50 flex justify-between bg-background/20">
        <button
          onClick={() => setShowFolderView((v) => !v)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg
                     text-xs border border-border/50 hover:bg-secondary"
        >
          <FolderTree className="w-4 h-4" />
          {showFolderView ? "Show Code" : "Show Files"}
        </button>

        <button
          onClick={() => setShowFolderView((v) => !v)}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg
                     text-xs text-muted-foreground hover:bg-secondary"
        >
          <FileIcon className="w-4 h-4 text-muted-foreground" />
          {activeFile?.name?.toUpperCase()}
        </button>

        {activeFile && (
          <div className="flex gap-1">
            {activeDiff && (
              <button
                type="button"
                onClick={() => setCodeDiffForFile(activeFile.path, null)}
                className="px-3 py-1.5 rounded-lg text-xs border border-amber-500/40 text-amber-600 dark:text-amber-400 hover:bg-amber-500/10"
                title="Hide diff overlay"
              >
                Exit diff
              </button>
            )}
            {/* EDIT */}
            <button
              onClick={() => {
                setIsEditing(true);
                setEditedContent(activeFile.content);
              }}
              className="px-3 py-1.5 rounded-lg text-xs hover:bg-secondary"
              disabled={!!activeDiff}
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>

            {/* SAVE */}
            {isEditing && (
              <button
                onClick={handleSave}
                className="px-3 py-1.5 rounded-lg text-xs hover:bg-secondary"
              >
                <Save className="w-3.5 h-3.5" />
              </button>
            )}

            <button
              onClick={handleCopy}
              className="px-3 py-1.5 rounded-lg text-xs hover:bg-secondary"
            >
              {copied ? (
                <Check className="w-3.5 h-3.5" />
              ) : (
                <Copy className="w-3.5 h-3.5" />
              )}
            </button>

            <button
              onClick={handleDownload}
              className="px-3 py-1.5 rounded-lg text-xs hover:bg-secondary"
            >
              <Download className="w-3.5 h-3.5" />
            </button>

            <button className="p-1.5 rounded-lg hover:bg-secondary">
              <Settings2 className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>

      {/* Viewer */}
      <div
        ref={codeScrollRef}
        onScroll={handleCodeScroll}
        className="flex-1 overflow-auto bg-[#011627] relative"
      >
        {showFolderView || !activeFile ? (
          <div className="p-4 text-sm bg-background/40">
            <div className="flex items-center gap-2 mb-3 text-primary font-semibold">
              <FolderTree className="w-4 h-4" />
              Project Structure
            </div>
            {renderTree(folderTree)}
          </div>
        ) : activeDiff ? (
          <DiffEditor
            height="100%"
            theme="vs-dark"
            original={activeDiff.before}
            modified={activeDiff.after}
            language={getLanguage(activeFile?.language || "tsx")}
            options={{
              readOnly: true,
              renderSideBySide: true,
              minimap: { enabled: false },
              fontSize: 13,
              scrollBeyondLastLine: false,
              renderOverviewRuler: true,
              diffWordWrap: "on",
            }}
          />
        ) : isEditing ? (
          <Editor
            height="100%"
            defaultLanguage={getLanguage(activeFile?.language)}
            value={editedContent}
            onChange={(value) => setEditedContent(value || "")}
            theme="vs-dark"
            onMount={(editor, monaco) => {
              // Add ambient type definitions for common libraries
              monaco.languages.typescript.typescriptDefaults.addExtraLib(
                TYPE_DEFINITIONS,
                "file:///node_modules/@types/ambient.d.ts"
              );

              // Configure TypeScript compiler options
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
              fontFamily: "monospace",
              minimap: { enabled: false },
              wordWrap: "on",
              automaticLayout: true,
              scrollBeyondLastLine: false,
              formatOnType: true,
              formatOnPaste: true,
            }}
          />
        ) : (
          <Highlight
            theme={themes.nightOwl}
            code={activeFile.content}
            language={activeFile.language}
          >
            {({ tokens, getLineProps, getTokenProps }) => (
              <pre className="text-[13px] p-4 font-mono">
                {tokens.map((line, i) => (
                  <div key={i} {...getLineProps({ line })}>
                    <span className="pr-6 text-slate-500 select-none">
                      {i + 1}
                    </span>
                    {line.map((token, key) => (
                      <span key={key} {...getTokenProps({ token })} />
                    ))}
                  </div>
                ))}
              </pre>
            )}
          </Highlight>
        )}
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
        <div className="px-4 py-2 border-t border-border/50 bg-secondary/30 text-xs text-muted-foreground flex justify-between">
          <span>
            {activeFile.language.toUpperCase()}
            {activeDiff ? (
              <span className="ml-2 text-amber-600 dark:text-amber-400">
                · diff (red removed, green added)
              </span>
            ) : null}
          </span>
          <span>{activeFile.content.split("\n").length} lines</span>
        </div>
      )}
    </div>
  );
}
