import { useEffect, useState } from "react";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { PreviewPanel } from "./PreviewPanel";
import { CodePanel } from "./CodePanel";
import { SplitPanel } from "./SplitPanel";
import { ChatContainer } from "../chat/ChatContainer";
import { SettingsPanel } from "../settings/SettingsPanel";
import { useParams } from "react-router-dom";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";
import { useAppData } from "@/context/useAppData";
import { ChatSearchProvider } from "@/context/ChatSearchContext";
import { FileTree } from "../project/FileTree";

export function DashboardLayout() {
  const getSavedTheme = () => {
    const raw = localStorage.getItem("nexus-theme");
    if (!raw) return "dark";
    try {
      return JSON.parse(raw);
    } catch {
      return raw;
    }
  };

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const { projectId } = useParams();

  const {
    projectFiles,
    selectedFile,
    setSelectedFile,
    setsingleProjectId,
    singleProjectId,
    loadProjectfiles,
    refreshData,
  } = useAppData();

  // ✅ When a project is clicked in sidebar
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(
    null,
  );

  // Panels
  const [previewOpen, setPreviewOpen] = useState(false);
  const [codeOpen, setCodeOpen] = useState(false);
  const [splitOpen, setSplitOpen] = useState(false);

  const [previewUrl, setPreviewUrl] = useState("");

  // Code + HTML preview storage
  const [generatedCode, setGeneratedCode] = useState("");
  const [generatedLanguage, setGeneratedLanguage] = useState("html");
  const [generatedHTML, setGeneratedHTML] = useState("");

  // Theme
  const [isDark, setIsDark] = useState(() => {
    const savedTheme = getSavedTheme();
    return savedTheme !== "light";
  });

  const [previousDarkTheme, setPreviousDarkTheme] = useState<string>(() => {
    const saved = localStorage.getItem("nexus-previous-dark-theme");
    if (!saved) return "dark";
    try {
      return JSON.parse(saved);
    } catch {
      return "dark";
    }
  });

  useEffect(() => {
    const root = document.documentElement;
    const savedTheme = getSavedTheme();

    root.classList.remove("light", "dark", "original", "gray", "custom");

    if (savedTheme === "light") {
      root.classList.add("light");
      setIsDark(false);
      return;
    }

    // "custom" background theme is no longer selectable; treat as dark for compatibility
    if (savedTheme === "custom") {
      root.classList.add("dark");
      setIsDark(true);
      return;
    }

    if (savedTheme === "dark" || savedTheme === "gray") {
      root.classList.add(savedTheme);
    }

    setIsDark(true);
  }, []);

  useEffect(() => {
    if (!singleProjectId) return;

    startPreview(singleProjectId);

    return () => {
      stopPreview(singleProjectId);
    };
  }, [singleProjectId]);

  const startPreview = async (project_Id: string) => {
    if (!project_Id) return;

    // Open the panel immediately — the URL arrives via SSE inside PreviewPanel
    setPreviewUrl("");
    setPreviewOpen(true);

    try {
      await fetch(
        `http://localhost:8000/preview/start/${project_Id}`,
        { method: "POST" },
      );
    } catch (e) {
      console.error("Preview start error:", e);
    }
  };

  const stopPreview = async (project_Id: string) => {
    if (!project_Id) return;
    const res = await fetch(
      `http://localhost:8000/preview/stop/${project_Id}`,
      {
        method: "POST",
      },
    );
    const data = await res.json();
    if (data.ok) {
      setPreviewUrl("");
      setPreviewOpen(false);
    }
  };

  const handleThemeToggle = () => {
    const root = document.documentElement;

    if (isDark) {
      const darkThemes = ["dark", "original", "gray", "custom"];
      const currentDark =
        darkThemes.find((t) => root.classList.contains(t)) || "dark";

      setPreviousDarkTheme(currentDark);
      localStorage.setItem(
        "nexus-previous-dark-theme",
        JSON.stringify(currentDark),
      );

      root.classList.remove("dark", "original", "gray", "custom");
      root.classList.add("light");
      localStorage.setItem("nexus-theme", '"light"');

      setIsDark(false);
    } else {
      root.classList.remove("light");
      root.classList.add(previousDarkTheme);

      localStorage.setItem("nexus-theme", JSON.stringify(previousDarkTheme));
      setIsDark(true);
    }
  };

  const openProjectInPanels = (
    code: string,
    language: string,
    html: string,
  ) => {
    setGeneratedCode(code);
    setGeneratedLanguage(language);
    setGeneratedHTML(html);

    setSplitOpen(false);
    setPreviewOpen(true);
    setCodeOpen(true);
  };
  const handlePreviewToggle = async () => {
    if (splitOpen) setSplitOpen(false);

    // If preview panel is closed → open it
    if (!previewOpen) {
      setPreviewOpen(true);

      // Start preview ONLY if not running
      if (!previewUrl && singleProjectId) {
        await startPreview(singleProjectId);
      }
    } else {
      // Just close the panel (do NOT stop server)
      setPreviewOpen(false);
    }
  };
  const handleCodeToggle = () => {
    if (splitOpen) setSplitOpen(false);
    setCodeOpen((prev) => !prev);
  };
  /** Closing split must also clear preview/code flags — otherwise the stacked panels stay open. */
  const closeSplitMode = () => {
    setSplitOpen(false);
    setPreviewOpen(false);
    setCodeOpen(false);
  };

  const handleSplitToggle = async () => {
    if (!splitOpen) {
      setSplitOpen(true);
      setPreviewOpen(true);
      setCodeOpen(true);

      if (!previewUrl && singleProjectId) {
        await startPreview(singleProjectId);
      }
    } else {
      closeSplitMode();
    }
  };

  const hasSidePanel = previewOpen || codeOpen || splitOpen;

  return (
    <ChatSearchProvider>
      <div
        className="h-screen w-full flex flex-col overflow-hidden bg-background relative"
        style={{ fontSize: "90%" }}
      >
        <FileTree files={projectFiles} onFileSelect={setSelectedFile} />
        {/* Ambient background */}
        <div className="fixed inset-0 pointer-events-none z-0">
          <div className="absolute top-0 left-1/4 w-80 h-80 bg-primary/4 rounded-full blur-3xl" />
          <div className="absolute bottom-0 right-1/4 w-80 h-80 bg-accent/4 rounded-full blur-3xl" />
        </div>

        {/* Top Bar */}
        <TopBar
          onSettingsClick={() => setSettingsOpen(true)}
          previewOpen={previewOpen}
          onOpenProject={openProjectInPanels}
          codeOpen={codeOpen}
          splitOpen={splitOpen}
          onPreviewToggle={handlePreviewToggle}
          onCodeToggle={handleCodeToggle}
          onSplitToggle={handleSplitToggle}
          isDark={isDark}
          onThemeToggle={handleThemeToggle}
        />

        {/* Main */}
        <div className="flex-1 flex overflow-hidden relative z-10">
          {/* Sidebar */}
          <Sidebar
            isOpen={sidebarOpen}
            onToggle={() => setSidebarOpen(!sidebarOpen)}
            onSettingsClick={() => setSettingsOpen(true)}
          />
          {/* Resizable Panels */}
          <ResizablePanelGroup direction="horizontal" className="flex-1">
            {/* Chat Area */}
            <ResizablePanel defaultSize={hasSidePanel ? 60 : 100} minSize={35}>
              <main className="h-full flex flex-col overflow-hidden pt-4">
                <ChatContainer
                  selectedchatId={selectedProjectId}
                  onCodeGenerated={(code, new_project_id) => {
                    refreshData();
                    setsingleProjectId(new_project_id);
                    loadProjectfiles(new_project_id);
                    setGeneratedCode(code);
                    setCodeOpen(true);
                    setPreviewOpen(true);
                  }}
                  onCodeEdited={(projectId) => {
                    refreshData();
                    setsingleProjectId(projectId);
                    loadProjectfiles(projectId);
                    setCodeOpen(true);
                  }}
                />
              </main>
            </ResizablePanel>

            {/* Preview Panel */}
            {previewOpen && !splitOpen && (
              <>
                <ResizableHandle
                  withHandle
                  className="bg-border/30 hover:bg-primary/30 transition-colors"
                />

                <ResizablePanel defaultSize={40} minSize={20} maxSize={50}>
                  <PreviewPanel
                    isOpen={previewOpen}
                    onClose={() => setPreviewOpen(false)}
                    previewUrl={previewUrl}
                    projectId={singleProjectId ?? undefined}
                    onUrlReady={(url) => setPreviewUrl(url)}
                  />
                </ResizablePanel>
              </>
            )}

            {/* Code Panel */}
            {codeOpen && !splitOpen && (
              <>
                <ResizableHandle
                  withHandle
                  className="bg-border/30 hover:bg-primary/30 transition-colors"
                />
                <ResizablePanel defaultSize={40} minSize={20} maxSize={50}>
                  <CodePanel
                    isOpen={!!selectedFile}
                    onClose={() => setCodeOpen(false)}
                  />
                </ResizablePanel>
              </>
            )}

            {/* Split Panel */}
            {splitOpen && (
              <>
                <ResizableHandle
                  withHandle
                  className="bg-border/30 hover:bg-accent/30 transition-colors"
                />
                <ResizablePanel defaultSize={40} minSize={25} maxSize={60}>
                  <SplitPanel
                    isOpen={splitOpen}
                    onClose={closeSplitMode}
                    previewUrl={previewUrl}
                  />
                </ResizablePanel>
              </>
            )}
          </ResizablePanelGroup>
        </div>

        {/* Settings Panel */}
        <SettingsPanel
          isOpen={settingsOpen}
          onClose={() => setSettingsOpen(false)}
          isDark={isDark}
          onThemeChange={setIsDark}
        />
      </div>
    </ChatSearchProvider>
  );
}
