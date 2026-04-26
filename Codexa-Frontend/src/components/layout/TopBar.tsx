import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import {
  ChevronDown,
  ChevronUp,
  Search,
  Sparkles,
  Code,
  Eye,
  Columns,
  Plus,
  Command,
  Zap,
  Moon,
  Sun,
  User,
  Settings,
  LogOut,
  CreditCard,
  HelpCircle,
  Crown,
  Activity,
  Check,
  MoreHorizontal,
  Pencil,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useAppData } from "@/context/useAppData";
import { useChatSearch } from "@/context/ChatSearchContext";
import { UsageModal } from "@/components/usage/UsageModal";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { API_BASE } from "@/lib/api";

interface Project {
  id: string;
  _id?: string;
  title: string;
  chat_id: string;
  code: string;
  code_language: string;
  emoji?: string;
  status: "active" | "paused" | "building";
}

interface TopBarProps {
  onSettingsClick: () => void;
  previewOpen: boolean;
  codeOpen: boolean;
  splitOpen: boolean;
  onPreviewToggle: () => void;
  onCodeToggle: () => void;
  onSplitToggle: () => void;
  onOpenProject: (code: string, language: string, html: string) => void;
  isDark: boolean;
  onThemeToggle: () => void;
}

export function TopBar({
  onSettingsClick,
  previewOpen,
  onOpenProject,
  codeOpen,
  splitOpen,
  onPreviewToggle,
  onCodeToggle,
  onSplitToggle,
  isDark,
  onThemeToggle,
}: TopBarProps) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);

  
  const [showProjectMenu, setShowProjectMenu] = useState(false);

  const [renameTarget, setRenameTarget] = useState<Project | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameBusy, setRenameBusy] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const [searchFocused, setSearchFocused] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [usageOpen, setUsageOpen] = useState(false);
  const navigate = useNavigate();
  const { user, userId, logout } = useAuth();

  const {
    userProjects,
    loadProjectfiles,
    setsingleProjectId,
    singleProjectId,
    refreshData,
  } = useAppData();

  const {
    query: chatSearchQuery,
    setQuery: setChatSearchQuery,
    debouncedQuery: chatSearchDebounced,
    hits: chatSearchHits,
    activeHitIndex,
    totalHits: chatSearchTotalHits,
    goToNext: chatSearchGoNext,
    goToPrev: chatSearchGoPrev,
    goToHit: chatSearchGoToHit,
    registerSearchInput,
    focusSearchInput,
    clearSearch,
  } = useChatSearch();

  useEffect(() => {
    setProjects(userProjects || []);
  }, [userProjects]);

  useEffect(() => {
    if (renameTarget) {
      setRenameValue(renameTarget.title);
    }
  }, [renameTarget]);

  useEffect(() => {
    const list = userProjects || [];
    if (!list.length) return;
    if (!singleProjectId) return;
    const match = list.find(
      (p: Project) =>
        p._id === singleProjectId || p.id === singleProjectId,
    );
    if (match) setActiveProject(match);
  }, [singleProjectId, userProjects]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        focusSearchInput();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [focusSearchInput]);

  const handleNewProject = () => {
    toast.success("Creating new project...", {
      description: "Your new project is being set up",
    });
    setShowProjectMenu(false);
  };

  const openRename = (project: Project) => {
    setShowProjectMenu(false);
    setRenameTarget(project);
  };

  const openDelete = (project: Project) => {
    setShowProjectMenu(false);
    setDeleteTarget(project);
  };

  const refreshProjects = async () => {
    if (!userId) return;

    try {
      const response = await fetch(`${API_BASE}/projects/${userId}`);
      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.detail || "Could not refresh projects");
      }

      const nextProjects = (data.projects || []) as Project[];
      setProjects(nextProjects);
      setActiveProject((current) => {
        const activeId = singleProjectId || current?._id || current?.id;
        if (!activeId) return current;

        return (
          nextProjects.find(
            (project) => (project._id ?? project.id) === activeId,
          ) ?? null
        );
      });
      refreshData();
    } catch {
      toast.error("Could not refresh projects");
    }
  };

  const submitRename = async () => {
    if (!userId || !renameTarget) return;

    const title = renameValue.trim();
    if (!title) {
      toast.error("Enter a name");
      return;
    }

    setRenameBusy(true);
    try {
      const response = await fetch(`${API_BASE}/projects/${renameTarget._id || renameTarget.id}?user_id=${encodeURIComponent(userId)}&title=${encodeURIComponent(title)}`, {
        method: "PATCH",
      });
      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.detail || "Rename failed");
      }

      toast.success("Project renamed");
      setRenameTarget(null);
      await refreshProjects();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Rename failed");
    } finally {
      setRenameBusy(false);
    }
  };

  const submitDelete = async () => {
    if (!userId || !deleteTarget) return;

    setDeleteBusy(true);
    try {
      const response = await fetch(
        `${API_BASE}/projects/${deleteTarget._id || deleteTarget.id}?user_id=${encodeURIComponent(userId)}`,
        { method: "DELETE" },
      );
      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.detail || "Delete failed");
      }

      toast.success("Project deleted");
      if (singleProjectId === (deleteTarget._id || deleteTarget.id)) {
        setsingleProjectId("");
        setActiveProject(null);
      }
      setDeleteTarget(null);
      await refreshProjects();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Delete failed");
    } finally {
      setDeleteBusy(false);
    }
  };

  const getStatusColor = (status: Project["status"]) => {
    switch (status) {
      case "active":
        return "bg-emerald-500";
      case "building":
        return "bg-amber-500 animate-pulse";
      case "paused":
        return "bg-muted-foreground";
    }
  };

  return (
    <>
    <header className="h-[58px] border-b border-border/70 dark:border-white/10 bg-background/80 dark:bg-white/5 backdrop-blur-xl shadow-sm shadow-black/10 dark:shadow-black/20 flex items-center justify-between pl-2 pr-5 lg:pl-3 lg:pr-7 z-50 relative">
      {/* Gradient line at bottom */}
      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-border/80 dark:via-primary/35 to-transparent" />

      {/* Left section - Logo and Project Selector (capped + truncate so center tabs never collide) */}
      <div className="flex min-w-0 flex-[1_1_0%] items-center gap-2 sm:gap-3 md:gap-4 max-w-[min(100%,14rem)] sm:max-w-[18rem] md:max-w-[20rem] lg:max-w-[22rem] xl:max-w-[24rem]">
        {/* Logo */}
        <div className="flex items-center gap-2.5 group cursor-pointer">
          <div
            aria-hidden="true"
            className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-[9px] bg-[linear-gradient(135deg,hsl(var(--primary)),#4f46e5)] shadow-[0_0_20px_hsl(var(--primary)/0.5)] transition-transform duration-200 group-hover:scale-105"
          >
            <Sparkles className="h-[18px] w-[18px] text-white" />
          </div>
          <div className="hidden sm:flex flex-col">
            <span className="font-bold text-base leading-tight tracking-tight bg-gradient-to-r from-foreground via-foreground to-primary bg-clip-text text-transparent transition-all duration-200 group-hover:drop-shadow-[0_0_10px_rgba(124,58,237,0.35)]">
              CODEXA
            </span>
            <div className="flex items-center gap-1">
              <Crown className="w-3 h-3 text-amber-500" />
              <span className="text-[10px] text-amber-500 font-medium">
                Pro
              </span>
            </div>
          </div>
        </div>

        {/* Divider */}
        <div className="hidden md:block w-px h-8 bg-gradient-to-b from-transparent via-border/70 dark:via-white/15 to-transparent" />

        {/* Project Selector */}
        <div className="relative min-w-0 flex-1">
          <button
            type="button"
            title={activeProject?.title || "recent projects"}
            onClick={() => setShowProjectMenu(!showProjectMenu)}
            className={cn(
              "flex w-full min-w-0 max-w-full items-center gap-2 px-2.5 sm:px-3 md:px-4 py-1 rounded-full transition-all duration-200 group border overflow-hidden",
              showProjectMenu
                ? "bg-background dark:bg-white/[0.08] border-border dark:border-white/15 ring-1 ring-border/80 dark:ring-white/10"
                : "bg-background/70 dark:bg-white/5 border-border/70 dark:border-white/10 hover:bg-background dark:hover:bg-white/10",
            )}
          >
            <div
              className={cn(
                "w-2 h-2 rounded-full border border-background shrink-0",
                getStatusColor("active"),
              )}
              aria-hidden="true"
            />
            <div className="flex min-w-0 flex-1 flex-col items-start text-left">
              <span className="w-full truncate text-sm font-semibold text-foreground leading-tight">
                {activeProject?.title || "Recent Projects"}
              </span>
              <span className="text-[10px] text-muted-foreground capitalize">
                {activeProject?.status ?? "active"}
              </span>
            </div>
            <ChevronDown
              className={cn(
                "w-4 h-4 shrink-0 text-muted-foreground transition-transform duration-300",
                showProjectMenu && "rotate-180",
              )}
            />
          </button>

          {showProjectMenu && (
            <>
              <div
                className="fixed inset-0 z-40"
                onClick={() => setShowProjectMenu(false)}
              />
              <div className="absolute left-0 top-full z-50 mt-1.5 w-full min-w-0 origin-top-left animate-fade-in-scale">
                <div
                  className={cn(
                    "overflow-hidden rounded-lg border bg-popover text-popover-foreground",
                    "border-border/90 dark:border-white/[0.1]",
                    "shadow-md shadow-black/5 dark:shadow-black/40",
                    "backdrop-blur-md",
                  )}
                >
                  <div className="flex items-center justify-between gap-2 border-b border-border/60 px-3 py-2 dark:border-white/[0.08]">
                    <span className="text-xs font-medium text-muted-foreground">
                      Recent projects
                    </span>
                    <span className="tabular-nums text-[11px] text-muted-foreground">
                      {projects.length}
                    </span>
                  </div>

                  <div
                    className={cn(
                      "max-h-[min(240px,40vh)] overflow-y-auto overflow-x-hidden py-1",
                      "scrollbar-thin",
                    )}
                  >
                    {projects.length === 0 ? (
                      <p className="px-3 py-5 text-center text-xs leading-relaxed text-muted-foreground">
                        No projects yet. Create one from chat.
                      </p>
                    ) : (
                      <ul className="px-1">
                        {projects.map((project) => {
                          const pid = project._id ?? project.id;
                          const selected =
                            Boolean(singleProjectId && pid === singleProjectId) ||
                            (!singleProjectId &&
                              activeProject &&
                              (activeProject._id === project._id ||
                                activeProject.id === project.id));
                          return (
                            <li key={pid || project.id} className="w-full">
                              <div className="group relative flex w-full min-w-0 items-center gap-0.5">
                                <button
                                  type="button"
                                  onClick={() => {
                                    const projId = project._id ?? project.id;
                                    setActiveProject(project);
                                    loadProjectfiles(projId);
                                    setShowProjectMenu(false);
                                    setsingleProjectId(projId);
                                    onOpenProject(
                                      project.code,
                                      project.code_language,
                                      project.code_language === "html"
                                        ? project.code
                                        : "",
                                    );
                                    toast.info(`Switched to ${project.title}`);
                                  }}
                                  className={cn(
                                    "flex min-w-0 flex-1 items-start gap-1.5 rounded-md pl-2 pr-1.5 py-1.5 text-left text-sm transition-colors",
                                    selected
                                      ? "bg-muted/90 font-medium text-foreground dark:bg-white/[0.08]"
                                      : "text-foreground/90 hover:bg-muted/50 dark:hover:bg-white/[0.05]",
                                  )}
                                >
                                  <div
                                    className={cn(
                                      "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full",
                                      getStatusColor(project.status),
                                    )}
                                    aria-hidden
                                  />
                                  <div className="min-w-0 flex-1">
                                    <div className="truncate leading-tight">
                                      {project.title}
                                    </div>
                                    <div className="mt-0.5 truncate text-[10px] capitalize text-muted-foreground">
                                      {project.status}
                                    </div>
                                  </div>
                                  {selected ? (
                                    <Check
                                      className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary"
                                      strokeWidth={2.5}
                                      aria-hidden
                                    />
                                  ) : (
                                    <span className="w-3.5 shrink-0" aria-hidden />
                                  )}
                                </button>

                                <DropdownMenu>
                                  <DropdownMenuTrigger asChild>
                                    <button
                                      type="button"
                                      aria-label={`More options for ${project.title}`}
                                      className={cn(
                                        "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-transparent text-[hsl(var(--muted-foreground))] transition-all duration-200",
                                        "hover:bg-[hsl(var(--foreground)/0.06)] hover:text-[hsl(var(--foreground))]",
                                        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--primary)/0.5)]",
                                        "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100",
                                      )}
                                    >
                                      <MoreHorizontal className="h-3.5 w-3.5" />
                                    </button>
                                  </DropdownMenuTrigger>
                                  <DropdownMenuContent
                                    align="end"
                                    sideOffset={4}
                                    className="w-44 border-[hsl(var(--foreground)/0.1)] bg-[hsl(var(--popover)/0.98)] text-[hsl(var(--popover-foreground))] backdrop-blur-xl"
                                  >
                                    <DropdownMenuItem
                                      className="cursor-pointer gap-2 text-[hsl(var(--popover-foreground))] focus:bg-[hsl(var(--primary)/0.18)] focus:text-[hsl(var(--foreground))]"
                                      onSelect={() => openRename(project)}
                                    >
                                      <Pencil className="h-4 w-4" />
                                      Rename
                                    </DropdownMenuItem>
                                    <DropdownMenuItem
                                      className="cursor-pointer gap-2 text-destructive transition-colors focus:bg-destructive/15 focus:text-destructive data-[highlighted]:bg-destructive/15 data-[highlighted]:text-destructive"
                                      onSelect={() => openDelete(project)}
                                    >
                                      <Trash2 className="h-4 w-4" />
                                      Delete
                                    </DropdownMenuItem>
                                  </DropdownMenuContent>
                                </DropdownMenu>
                              </div>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>

                  <div className="border-t border-border/60 p-1 dark:border-white/[0.08]">
                    <button
                      type="button"
                      onClick={handleNewProject}
                      className={cn(
                        "flex w-full items-center justify-center gap-2 rounded-md py-2 text-xs font-medium",
                        "text-muted-foreground transition-colors",
                        "hover:bg-muted/60 hover:text-foreground dark:hover:bg-white/[0.06]",
                      )}
                    >
                      <Plus className="h-3.5 w-3.5" strokeWidth={2} />
                      New project
                    </button>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Center - View Mode Tabs */}
      <div className="hidden md:flex flex-[0_0_auto] items-center justify-center px-2 lg:px-4">
        <div className="flex shrink-0 items-center gap-0.5 sm:gap-1 p-1 rounded-full bg-background/70 dark:bg-white/5 border border-border/70 dark:border-white/10 backdrop-blur-md shadow-sm">
          {[
            {
              id: "preview",
              label: "Preview",
              icon: Eye,
              isActive: previewOpen && !splitOpen,
              onClick: onPreviewToggle,
            },
            {
              id: "code",
              label: "Code",
              icon: Code,
              isActive: codeOpen && !splitOpen,
              onClick: onCodeToggle,
            },
            {
              id: "split",
              label: "Split",
              icon: Columns,
              isActive: splitOpen,
              onClick: onSplitToggle,
              accent: true,
            },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={tab.onClick}
              className={cn(
                "relative flex items-center gap-2 px-3.5 py-1 rounded-full text-sm font-medium transition-all duration-200",
                tab.isActive
                  ? tab.accent
                    ? "bg-gradient-to-r from-accent to-primary text-white shadow-md shadow-primary/25"
                    : "bg-gradient-to-r from-primary to-primary/80 text-primary-foreground shadow-md shadow-primary/25"
                  : "text-muted-foreground bg-background/70 dark:bg-white/5 hover:bg-background dark:hover:bg-white/10 hover:text-foreground",
              )}
            >
              <tab.icon className="w-4 h-4" />
              <span>{tab.label}</span>
              {tab.isActive && (
                <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Right section - Search & Actions */}
      <div className="flex items-center gap-3 shrink-0">
        {/* Search — in-chat find (Word-style navigation) */}
        <div className="hidden lg:block relative min-w-0">
          <div
            className={cn(
              "flex items-center gap-2 px-3.5 py-1.5 rounded-full border backdrop-blur-md transition-all duration-200 min-w-0 shadow-sm",
              searchFocused
                ? "bg-background/90 dark:bg-white/10 border-primary/40 ring-2 ring-primary/20 w-56 xl:w-64 shadow-md shadow-primary/10"
                : "bg-background/75 dark:bg-white/5 border-border/70 dark:border-white/10 hover:bg-background/95 dark:hover:bg-white/10 w-56 xl:w-64",
            )}
          >
            <Search className="w-4 h-4 shrink-0 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search in chat..."
              value={chatSearchQuery}
              ref={registerSearchInput}
              aria-label="Search messages in this chat"
              aria-expanded={
                searchFocused &&
                !!chatSearchQuery.trim() &&
                (chatSearchTotalHits > 0 || !!chatSearchDebounced.trim())
              }
              aria-controls="chat-search-results"
              className="min-w-0 flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground/80 focus:outline-none"
              onChange={(e) => setChatSearchQuery(e.target.value)}
              onFocus={() => setSearchFocused(true)}
              onBlur={() => {
                window.setTimeout(() => setSearchFocused(false), 120);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  if (e.shiftKey) chatSearchGoPrev();
                  else chatSearchGoNext();
                }
                if (e.key === "Escape") {
                  clearSearch();
                  (e.target as HTMLInputElement).blur();
                }
              }}
            />
            <kbd className="hidden sm:flex items-center gap-0.5 px-1.5 py-0.5 rounded-full bg-background/80 dark:bg-white/10 border border-border/70 dark:border-white/15 text-[10px] text-muted-foreground shrink-0">
              <Command className="w-2.5 h-2.5" />K
            </kbd>
          </div>

          {searchFocused && chatSearchQuery.trim() !== "" && (
            <div
              id="chat-search-results"
              role="listbox"
              className="absolute right-0 top-[calc(100%+6px)] z-[60] w-[min(100vw-2rem,22rem)] rounded-xl border border-border/80 bg-popover/95 dark:bg-[#14161c]/95 text-foreground shadow-lg shadow-black/15 ring-1 ring-black/5 dark:ring-white/10 backdrop-blur-md overflow-hidden"
              onMouseDown={(e) => e.preventDefault()}
            >
              <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-border/60 bg-muted/30">
                <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">
                  In this chat
                </span>
                {chatSearchDebounced.trim() && chatSearchTotalHits > 0 ? (
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      title="Previous result (Shift+Enter)"
                      onClick={() => chatSearchGoPrev()}
                      className="p-1 rounded-md text-muted-foreground hover:bg-background/80 hover:text-foreground transition-colors"
                    >
                      <ChevronUp className="w-4 h-4" />
                    </button>
                    <span className="text-xs tabular-nums text-muted-foreground min-w-[4.5rem] text-center">
                      {activeHitIndex + 1} of {chatSearchTotalHits}
                    </span>
                    <button
                      type="button"
                      title="Next result (Enter)"
                      onClick={() => chatSearchGoNext()}
                      className="p-1 rounded-md text-muted-foreground hover:bg-background/80 hover:text-foreground transition-colors"
                    >
                      <ChevronDown className="w-4 h-4" />
                    </button>
                  </div>
                ) : null}
              </div>

              {!chatSearchDebounced.trim() ? (
                <p className="px-3 py-3 text-xs text-muted-foreground">
                  Keep typing…
                </p>
              ) : chatSearchTotalHits === 0 ? (
                <p className="px-3 py-3 text-xs text-muted-foreground">
                  No matches in this conversation.
                </p>
              ) : (
                <ul className="max-h-52 overflow-y-auto py-1 scrollbar-thin">
                  {chatSearchHits.map((hit, i) => (
                    <li key={`${hit.messageId}-${hit.offset}-${i}`}>
                      <button
                        type="button"
                        role="option"
                        aria-selected={i === activeHitIndex}
                        onClick={() => chatSearchGoToHit(i)}
                        className={cn(
                          "w-full text-left px-3 py-2 text-xs leading-snug transition-colors",
                          i === activeHitIndex
                            ? "bg-primary/12 text-foreground"
                            : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
                        )}
                      >
                        <span className="line-clamp-2 break-words">
                          {hit.snippet}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        {/* Divider */}
        <div className="hidden lg:block w-px h-8 bg-gradient-to-b from-transparent via-border/70 dark:via-white/15 to-transparent mx-1" />

        {/* Action Buttons */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={onThemeToggle}
            className="relative p-2 rounded-full bg-background/70 dark:bg-white/5 border border-border/70 dark:border-white/10 hover:bg-background dark:hover:bg-white/10 transition-all duration-200 text-muted-foreground hover:text-foreground group"
            title={isDark ? "Switch to Light Mode" : "Switch to Dark Mode"}
          >
            {isDark ? (
              <Sun className="w-5 h-5 group-hover:scale-110 group-hover:rotate-90 transition-all duration-300 text-amber-500" />
            ) : (
              <Moon className="w-5 h-5 group-hover:scale-110 transition-transform text-primary" />
            )}
          </button>

          <button
            type="button"
            onClick={() => setUsageOpen(true)}
            className="relative p-2 rounded-full bg-background/70 dark:bg-white/5 border border-border/70 dark:border-white/10 hover:bg-background dark:hover:bg-white/10 transition-all duration-200 text-muted-foreground hover:text-foreground group"
            title="Usage"
          >
            <Activity className="w-5 h-5 group-hover:scale-110 transition-transform" />
            <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-emerald-500 rounded-full" />
          </button>
        </div>

        {/* Divider */}
        <div className="w-px h-8 bg-gradient-to-b from-transparent via-border/70 dark:via-white/15 to-transparent mx-1" />

        {/* User Avatar with Dropdown */}
        <div className="relative">
          <button
            onClick={() => setShowUserMenu(!showUserMenu)}
            className={cn(
              "flex items-center gap-3 px-2.5 py-1 rounded-full transition-all duration-200 group border",
              showUserMenu
                ? "bg-background dark:bg-white/10 border-border/70 dark:border-white/20"
                : "bg-background/70 dark:bg-white/5 border-border/70 dark:border-white/10 hover:bg-background dark:hover:bg-white/10",
            )}
          >
            <div className="relative">
              <div className="w-7 h-7 rounded-full bg-gradient-to-br from-violet-500 via-purple-500 to-fuchsia-500 flex items-center justify-center text-xs font-bold text-white shadow-md shadow-purple-500/20 transition-all duration-200 group-hover:scale-105">
                {user?.avatarUrl ? (
                  <img
                    src={user.avatarUrl}
                    alt="Profile avatar"
                    className="h-full w-full rounded-full object-cover"
                  />
                ) : user?.name ? (
                  user.name.charAt(0).toUpperCase() +
                  user.name.charAt(1).toUpperCase()
                ) : (
                  "U"
                )}
              </div>
              <div className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-500 border-2 border-background" />
            </div>
            <div className="hidden xl:flex flex-col items-start">
              <span className="text-sm font-size-10px text-foreground leading-tight">
                {user?.name ? user?.name : "User Name"}
              </span>
              <span className="text-[9px] text-muted-foreground">Pro Plan</span>
            </div>
            <ChevronDown
              className={cn(
                "hidden xl:block w-4 h-4 text-muted-foreground transition-transform duration-300",
                showUserMenu && "rotate-180",
              )}
            />
          </button>

          {/* User Dropdown Menu */}
          {showUserMenu && (
            <>
              <div
                className="fixed inset-0 z-40"
                onClick={() => setShowUserMenu(false)}
              />
              <div className="absolute top-full mt-2 right-0 w-60 z-50 animate-fade-in-scale">
                <div className="bg-background/95 dark:bg-popover border border-border shadow-xl shadow-black/20 ring-1 ring-black/5 dark:ring-white/10 rounded-xl overflow-hidden backdrop-blur-sm">
                  {/* User Info Header */}
                  <div className="px-4 py-3.5 border-b border-border/60 bg-secondary/30">
                    <div className="flex items-center gap-3">
                      <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-violet-500 via-purple-500 to-fuchsia-500 flex items-center justify-center text-lg font-bold text-white shadow-sm">
                        {user?.avatarUrl ? (
                          <img
                            src={user.avatarUrl}
                            alt="Profile avatar"
                            className="h-full w-full rounded-xl object-cover"
                          />
                        ) : user?.name ? (
                          user.name.charAt(0).toUpperCase() +
                          user.name.charAt(1).toUpperCase()
                        ) : (
                          "U"
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-semibold text-foreground truncate">
                          {user.name ? user.name : "User Name"}
                        </p>
                        <p className="text-xs text-muted-foreground truncate">
                          {user.email ? user.email : "john@example.com"}
                        </p>
                        <div className="flex items-center gap-1 mt-1">
                          <Crown className="w-3 h-3 text-amber-500" />
                          <span className="text-xs text-amber-500 font-medium">
                            Pro Plan
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Menu Items */}
                  <div className="p-2">
                    <button
                      onClick={() => {
                        onSettingsClick();
                        setShowUserMenu(false);
                      }}
                      className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-foreground transition-all duration-200 hover:bg-[hsl(var(--primary)/0.18)] hover:text-[hsl(var(--foreground))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--primary)/0.35)]"
                    >
                      <User className="w-4 h-4 text-muted-foreground" />
                      <span>Profile Settings</span>
                    </button>
                    <button
                      onClick={() => {
                        onSettingsClick();
                        setShowUserMenu(false);
                      }}
                      className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-foreground transition-all duration-200 hover:bg-[hsl(var(--primary)/0.18)] hover:text-[hsl(var(--foreground))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--primary)/0.35)]"
                    >
                      <Settings className="w-4 h-4 text-muted-foreground" />
                      <span>Account Settings</span>
                    </button>
                    <button
                      onClick={() => {
                        toast.info("Billing page coming soon");
                        setShowUserMenu(false);
                      }}
                      className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-foreground transition-all duration-200 hover:bg-[hsl(var(--primary)/0.18)] hover:text-[hsl(var(--foreground))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--primary)/0.35)]"
                    >
                      <CreditCard className="w-4 h-4 text-muted-foreground" />
                      <span>Billing & Plans</span>
                    </button>
                    <button
                      onClick={() => {
                        toast.info("Help center coming soon");
                        setShowUserMenu(false);
                      }}
                      className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-foreground transition-all duration-200 hover:bg-[hsl(var(--primary)/0.18)] hover:text-[hsl(var(--foreground))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--primary)/0.35)]"
                    >
                      <HelpCircle className="w-4 h-4 text-muted-foreground" />
                      <span>Help & Support</span>
                    </button>
                  </div>

                  {/* Logout */}
                  <div className="p-2 border-t border-border/60">
                    <button
                      onClick={() => {
                        logout();
                        toast.success("Logged out successfully");
                        setShowUserMenu(false);
                        navigate("/auth?mode=login", { replace: true });
                      }}
                      className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-destructive hover:bg-destructive/10 transition-all duration-200"
                    >
                      <LogOut className="w-4 h-4" />
                      <span>Log Out</span>
                    </button>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
    <UsageModal open={usageOpen} onClose={() => setUsageOpen(false)} isDark={isDark} />

    {/* Rename Project Dialog */}
    <Dialog open={!!renameTarget} onOpenChange={(open) => !open && setRenameTarget(null)}>
      <DialogContent className="z-[110] overflow-hidden border-white/10 bg-[#101119]/95 text-zinc-100 backdrop-blur-xl sm:max-w-md">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,hsl(var(--primary)/0.22),transparent_42%),linear-gradient(180deg,rgba(255,255,255,0.04),transparent_38%)]" />
        <DialogHeader>
          <div className="relative mb-1 flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-[hsl(var(--primary)/0.18)] bg-[linear-gradient(135deg,hsl(var(--primary)/0.24),hsl(var(--primary)/0.12))] shadow-[0_12px_30px_hsl(var(--primary)/0.24)]">
              <Pencil className="h-4 w-4 text-white" />
            </div>
            <div>
              <DialogTitle className="text-xl text-white">Rename project</DialogTitle>
              <DialogDescription className="mt-1 text-zinc-400">
                Give this project a sharper, cleaner identity in your workspace.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>
        <div className="relative mt-2 rounded-[26px] border border-white/10 bg-white/[0.045] p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.24em] text-zinc-500">
            New title
          </p>
          <Input
            value={renameValue}
            onChange={(event) => setRenameValue(event.target.value)}
            placeholder="Project name"
            onKeyDown={(event) => event.key === "Enter" && submitRename()}
            className="h-12 rounded-2xl border-white/10 bg-[hsl(var(--background)/0.78)] text-base text-zinc-100 placeholder:text-zinc-500"
          />
          <div className="mt-3 flex items-center justify-between text-xs text-zinc-500">
            <span className="truncate">Visible in your project list</span>
            <span>{renameValue.trim().length}/60</span>
          </div>
        </div>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={() => setRenameTarget(null)} className="border-white/10 bg-white/[0.03]">
            Cancel
          </Button>
          <Button
            onClick={submitRename}
            disabled={renameBusy}
            className="bg-[linear-gradient(135deg,hsl(var(--primary)),hsl(var(--primary)/0.88)_50%,hsl(var(--primary)/0.72))] text-[hsl(var(--primary-foreground))] shadow-[0_12px_30px_hsl(var(--primary)/0.28)] hover:opacity-95"
          >
            {renameBusy ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    {/* Delete Project Confirmation Dialog */}
    <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
      <AlertDialogContent className="z-[110] overflow-hidden border-white/10 bg-[#101119]/95 text-zinc-100 backdrop-blur-xl">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,hsl(var(--primary)/0.22),transparent_42%),linear-gradient(180deg,rgba(255,255,255,0.04),transparent_38%)]" />
        <AlertDialogHeader>
          <div className="relative mb-1 flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-red-500/30 bg-red-500/10 shadow-[0_12px_30px_rgba(239,68,68,0.24)]">
              <Trash2 className="h-4 w-4 text-red-400" />
            </div>
            <div>
              <AlertDialogTitle className="text-xl text-white">Delete project</AlertDialogTitle>
              <AlertDialogDescription className="mt-1 text-zinc-400">
                Are you sure you want to delete <span className="text-foreground font-semibold">{deleteTarget?.title}</span>? This action cannot be undone.
              </AlertDialogDescription>
            </div>
          </div>
        </AlertDialogHeader>
        <AlertDialogFooter className="gap-2 sm:gap-0">
          <AlertDialogCancel asChild>
            <Button variant="outline" className="border-white/10 bg-white/[0.03]">
              Cancel
            </Button>
          </AlertDialogCancel>
          <AlertDialogAction asChild>
            <Button
              onClick={submitDelete}
              disabled={deleteBusy}
              className="bg-red-600 text-white shadow-[0_12px_30px_rgba(239,68,68,0.28)] hover:bg-red-700"
            >
              {deleteBusy ? "Deleting..." : "Delete"}
            </Button>
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
    </>
  );
}
