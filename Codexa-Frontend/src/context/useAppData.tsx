import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { useAuth } from "./AuthContext";
import { detectLanguage } from "@/lib/detectLanguage";

/* ----------------------------------------
   Single source of truth
---------------------------------------- */
export interface ProjectFile {
  _id: string;
  path: string;
  content: string;
  language: string; // derived
  name: string; // derived
}

/** Server-sent before/after for a single file (optional unified_diff from backend). */
export interface CodeFileDiff {
  file: string;
  type: string;
  before: string;
  after: string;
  unified_diff?: string;
  /** Client-side timestamp (ms) of when the diff arrived. Used for entry animations. */
  receivedAt?: number;
}

/* ----------------------------------------
   Context Type
---------------------------------------- */
interface AppDataContextType {
  refreshData: () => void;
  userChats: any[];
  userProjects: any[];
  chatIds: string[];
  projectIds: string[];
  singleProjectId: string;
  setsingleProjectId: (projectId: string) => void;
  projectFiles: ProjectFile[];

  selectedFile: ProjectFile | null;
  setSelectedFile: (file: ProjectFile | null) => void;

  /** Paths keyed by project-relative file path (e.g. frontend/src/App.tsx). */
  codeDiffsByPath: Record<string, CodeFileDiff>;
  mergeCodeDiffs: (changes: CodeFileDiff[]) => void;
  setCodeDiffForFile: (path: string, diff: CodeFileDiff | null) => void;
  clearCodeDiffs: () => void;
  /** Ordered list of paths most recently edited (newest first), for a "recent changes" strip. */
  recentEditedPaths: string[];
  /** Path of the single most-recently edited file, or null. */
  latestEditedPath: string | null;

  fetchUserChats: () => Promise<void>;
  fetchUserProjects: () => Promise<void>;
  loadProjectfiles: (projectId: string) => Promise<void>;
}

/* ----------------------------------------
   Context
---------------------------------------- */
const AppDataContext = createContext<AppDataContextType | null>(null);

/* ----------------------------------------
   Provider
---------------------------------------- */
export const AppDataProvider = ({
  children,
}: {
  children: React.ReactNode;
}) => {
  const { userId } = useAuth();

  const [userChats, setUserChats] = useState<any[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [userProjects, setUserProjects] = useState<any[]>([]);
  const [chatIds, setChatIds] = useState<string[]>([]);
  const [projectIds, setProjectIds] = useState<string[]>([]);
  const [singleProjectId, setsingleProjectId] = useState<string>();
  const [projectFiles, setProjectFiles] = useState<ProjectFile[]>([]);
  const [selectedFile, setSelectedFile] = useState<ProjectFile | null>(null);
  const [codeDiffsByPath, setCodeDiffsByPath] = useState<
    Record<string, CodeFileDiff>
  >({});
  const [recentEditedPaths, setRecentEditedPaths] = useState<string[]>([]);

  const mergeCodeDiffs = useCallback((changes: CodeFileDiff[]) => {
    if (!changes?.length) return;
    const now = Date.now();
    setCodeDiffsByPath((prev) => {
      const next = { ...prev };
      for (const c of changes) {
        if (c?.file) next[c.file] = { ...c, receivedAt: now };
      }
      return next;
    });
    setRecentEditedPaths((prev) => {
      const incoming = changes.map((c) => c?.file).filter(Boolean) as string[];
      const merged = [...incoming, ...prev.filter((p) => !incoming.includes(p))];
      return merged.slice(0, 20);
    });
  }, []);

  const setCodeDiffForFile = useCallback(
    (path: string, diff: CodeFileDiff | null) => {
      setCodeDiffsByPath((prev) => {
        const next = { ...prev };
        if (diff) next[path] = { ...diff, receivedAt: Date.now() };
        else delete next[path];
        return next;
      });
    },
    [],
  );

  const clearCodeDiffs = useCallback(() => {
    setCodeDiffsByPath({});
    setRecentEditedPaths([]);
  }, []);

  const latestEditedPath = recentEditedPaths[0] ?? null;

  /* ----------------------------------------
     Fetch user chats
  ---------------------------------------- */
  const fetchUserChats = async () => {
    if (!userId) return;

    try {
      const res = await fetch(`http://localhost:8000/chat/get-chats/${userId}`);
      const data = await res.json();

      if (data.ok) {
        setUserChats(data.chats);
        setChatIds(data.chats.map((c: any) => c._id));
      }
    } catch (err) {
      console.error("Failed to fetch chats", err);
    }
  };

  /* ----------------------------------------
     Fetch user projects
  ---------------------------------------- */
  const fetchUserProjects = async () => {
    if (!userId) return;

    try {
      const res = await fetch(`http://localhost:8000/projects/${userId}`);
      const data = await res.json();

      if (data.ok) {
        setUserProjects(data.projects);
        setProjectIds(data.projects.map((p: any) => p._id));
      }
    } catch (err) {
      console.error("Failed to fetch projects", err);
    }
  };

  const refreshData = () => {
    setRefreshKey((prev) => prev + 1);
  };

  /* ----------------------------------------
     Load project files
     → Default select App.tsx
  ---------------------------------------- */
  const loadProjectfiles = async (projectId: string) => {
    if (!projectId) return;

    try {
      const res = await fetch(`http://localhost:8000/files/${projectId}`);
      const data = await res.json();

      if (data.ok) {
        const enrichedFiles: ProjectFile[] = data.files
          .filter((file: any) => file.path != null)
          .map((file: any) => ({
            _id: file._id,
            path: file.path,
            content: file.content ?? "",
            language: detectLanguage(file.path),
            name: file.path.split("/").pop() ?? file.path,
          }));

        setProjectFiles(enrichedFiles);

        // ✅ Default file selection logic
        const defaultFile =
          enrichedFiles.find((f) => f.name?.toLowerCase() === "app.tsx") ||
          enrichedFiles[0] ||
          null;

        setSelectedFile(defaultFile);
      }
    } catch (err) {
      console.error("Failed to load project files:", err);
    }
  };

  /* ----------------------------------------
     Auto load on app start
  ---------------------------------------- */
  useEffect(() => {
    fetchUserChats();
    fetchUserProjects();
  }, [userId, refreshKey]);

  return (
    <AppDataContext.Provider
      value={{
        userChats,
        userProjects,
        chatIds,
        singleProjectId,
        setsingleProjectId,
        projectIds,
        projectFiles,
        selectedFile,
        setSelectedFile,
        fetchUserChats,
        fetchUserProjects,
        loadProjectfiles,
        refreshData,
        codeDiffsByPath,
        mergeCodeDiffs,
        setCodeDiffForFile,
        clearCodeDiffs,
        recentEditedPaths,
        latestEditedPath,
      }}
    >
      {children}
    </AppDataContext.Provider>
  );
};

/* ----------------------------------------
   Hook
---------------------------------------- */
export const useAppData = () => {
  const context = useContext(AppDataContext);
  if (!context) {
    throw new Error("useAppData must be used within AppDataProvider");
  }
  return context;
};
