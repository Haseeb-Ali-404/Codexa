import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/utils";
import { API_BASE } from "@/lib/api";
import { useNavigate, useParams } from "react-router-dom";
import {
  PanelLeftClose,
  Copy,
  Facebook,
  Mail,
  Linkedin,
  MessageCircle,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Send,
  Settings,
  Share2,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useAppData } from "@/context/useAppData";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
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
import { toast } from "sonner";

interface Chat {
  id: string;
  title: string;
}

interface SidebarProps {
  isOpen: boolean;
  onToggle: () => void;
  onSettingsClick: () => void;
}

function chatShareUrl(chatId: string) {
  const origin = window.location.origin.replace(/\/$/, "");
  return `${origin}/c/${chatId}`;
}

function shareBlurb(title: string, url: string) {
  return `Chat on CODEXA: ${title}\n${url}`;
}

function SidebarSkeleton({ isOpen }: { isOpen: boolean }) {
  return (
    <div className={cn("space-y-2 px-1 pb-3", !isOpen && "space-y-3")}>
      {Array.from({ length: 6 }).map((_, index) => (
        <div
          key={index}
          className={cn(
            "rounded-2xl border border-[hsl(var(--foreground)/0.06)] bg-[hsl(var(--foreground)/0.03)] p-2",
            "shadow-[inset_0_1px_0_hsl(var(--foreground)/0.03)]",
            !isOpen && "flex justify-center p-1.5",
          )}
        >
          {isOpen ? (
            <div className="space-y-1.5">
              <Skeleton className="h-3.5 w-3/4 rounded-full bg-[hsl(var(--foreground)/0.06)]" />
              <Skeleton className="h-2.5 w-1/3 rounded-full bg-[hsl(var(--foreground)/0.04)]" />
            </div>
          ) : (
            <Skeleton className="h-8 w-8 rounded-2xl bg-[hsl(var(--foreground)/0.06)]" />
          )}
        </div>
      ))}
    </div>
  );
}

function EmptyChats({
  isOpen,
  searchQuery,
}: {
  isOpen: boolean;
  searchQuery: string;
}) {
  if (!isOpen) {
    return (
      <div className="flex justify-center px-1 py-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-2xl border border-dashed border-[hsl(var(--foreground)/0.1)] bg-[hsl(var(--foreground)/0.03)] text-[11px] font-semibold text-[hsl(var(--muted-foreground))]">
          0
        </div>
      </div>
    );
  }

  return (
    <div className="mx-1 mt-3 rounded-[22px] border border-[hsl(var(--foreground)/0.08)] bg-[hsl(var(--foreground)/0.035)] px-4 py-4 text-center shadow-[inset_0_1px_0_hsl(var(--foreground)/0.04)] backdrop-blur-xl">
      <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-[linear-gradient(135deg,hsl(var(--primary)/0.2),hsl(var(--primary)/0.1))] text-[hsl(var(--foreground))] shadow-[0_0_30px_hsl(var(--primary)/0.18)]">
        <Sparkles className="h-5 w-5" />
      </div>
      <p className="text-sm font-semibold text-[hsl(var(--foreground))]">
        {searchQuery ? "No chats match your search" : "No chats yet"}
      </p>
      <p className="mt-1 text-xs leading-5 text-[hsl(var(--muted-foreground))]">
        {searchQuery
          ? "Try a different keyword or clear the search to see everything."
          : "Start a new conversation to build your CODEXA workspace."}
      </p>
    </div>
  );
}

function ShareOptionButton({
  label,
  icon,
  onClick,
}: {
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group relative overflow-hidden rounded-2xl border border-[hsl(var(--foreground)/0.1)] bg-[linear-gradient(180deg,hsl(var(--foreground)/0.06),hsl(var(--foreground)/0.025))] px-3 py-3 text-left",
        "transition-all duration-300 hover:-translate-y-0.5 hover:border-[hsl(var(--primary)/0.28)] hover:shadow-[0_12px_30px_hsl(var(--primary)/0.18)]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--primary)/0.5)]",
      )}
    >
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,hsl(var(--primary)/0.18),transparent_55%)] opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
      <div className="relative flex flex-col items-start gap-2">
        <span className="flex h-10 w-10 items-center justify-center rounded-2xl border border-[hsl(var(--foreground)/0.1)] bg-[hsl(var(--foreground)/0.06)] text-[hsl(var(--foreground))]">
          {icon}
        </span>
        <span className="text-xs font-medium text-[hsl(var(--foreground))]">{label}</span>
      </div>
    </button>
  );
}

export function Sidebar({ isOpen, onToggle, onSettingsClick }: SidebarProps) {
  const { userId } = useAuth();
  const { userChats, fetchUserChats } = useAppData();
  const navigate = useNavigate();
  const { chatId } = useParams();

  const [chats, setChats] = useState<Chat[]>([]);
  const [activeChat, setActiveChat] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [hasSyncedChats, setHasSyncedChats] = useState(false);

  const [renameTarget, setRenameTarget] = useState<Chat | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameBusy, setRenameBusy] = useState(false);

  const [shareTarget, setShareTarget] = useState<Chat | null>(null);

  const [deleteTarget, setDeleteTarget] = useState<Chat | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  useEffect(() => {
    if (!userId) {
      setChats([]);
      setHasSyncedChats(true);
      return;
    }

    const formatted = userChats.map((p: { _id?: string; id?: string; title?: string }) => ({
      id: p._id || p.id || "",
      title: p.title || "Untitled Chat",
    }));

    setChats(formatted);
    setActiveChat(chatId || "");
    setHasSyncedChats(true);
  }, [userId, chatId, userChats]);

  useEffect(() => {
    if (renameTarget) {
      setRenameValue(renameTarget.title);
    }
  }, [renameTarget]);

  const filteredChats = useMemo(
    () =>
      chats.filter((chat) =>
        chat.title.toLowerCase().includes(searchQuery.trim().toLowerCase()),
      ),
    [chats, searchQuery],
  );

  const isLoadingChats = !!userId && !hasSyncedChats;
  const showSearchClear = searchQuery.length > 0;

  const handleProjectClick = (selectedChatId: string) => {
    navigate(`/c/${selectedChatId}`);
    setActiveChat(selectedChatId);
  };

  const handleNewChat = () => {
    navigate("/");
    setActiveChat("");
  };

  const openRename = (chat: Chat) => {
    setRenameTarget(chat);
  };

  const openShare = (chat: Chat) => {
    setShareTarget(chat);
  };

  const openDelete = (chat: Chat) => {
    setDeleteTarget(chat);
  };

  const refreshChats = async () => {
    try {
      await fetchUserChats();
    } catch {
      toast.error("Could not refresh chats");
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
      const response = await fetch(`${API_BASE}/chat/${renameTarget.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, title }),
      });
      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.detail || "Rename failed");
      }

      toast.success("Chat renamed");
      setRenameTarget(null);
      await refreshChats();
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
        `${API_BASE}/chat/${deleteTarget.id}?user_id=${encodeURIComponent(userId)}`,
        { method: "DELETE" },
      );
      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.detail || "Delete failed");
      }

      toast.success("Chat deleted");
      if (activeChat === deleteTarget.id) {
        navigate("/");
        setActiveChat("");
      }
      setDeleteTarget(null);
      await refreshChats();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Delete failed");
    } finally {
      setDeleteBusy(false);
    }
  };

  const copyShareLink = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url);
      toast.success("Link copied");
    } catch {
      toast.error("Could not copy");
    }
  };

  const shareUrl = shareTarget ? chatShareUrl(shareTarget.id) : "";
  const shareText = shareTarget ? shareBlurb(shareTarget.title, shareUrl) : "";

  const openExternalShare = (kind: string) => {
    if (!shareUrl) return;

    const encodedUrl = encodeURIComponent(shareUrl);
    const text = encodeURIComponent(shareText);
    const urls: Record<string, string> = {
      whatsapp: `https://wa.me/?text=${text}`,
      telegram: `https://t.me/share/url?url=${encodedUrl}&text=${encodeURIComponent(shareTarget?.title || "CODEXA chat")}`,
      twitter: `https://twitter.com/intent/tweet?text=${text}`,
      facebook: `https://www.facebook.com/sharer/sharer.php?u=${encodedUrl}`,
      linkedin: `https://www.linkedin.com/sharing/share-offsite/?url=${encodedUrl}`,
      email: `mailto:?subject=${encodeURIComponent(`CODEXA: ${shareTarget?.title || "Chat"}`)}&body=${text}`,
    };

    const url = urls[kind];
    if (url) {
      window.open(url, "_blank", "noopener,noreferrer");
    }
  };

  return (
    <aside
      className={cn(
        "relative flex h-full flex-col overflow-hidden border-r border-[hsl(var(--sidebar-border)/0.7)] bg-[hsl(var(--sidebar-background)/0.96)] text-[hsl(var(--sidebar-foreground))] backdrop-blur-2xl",
        "shadow-[0_20px_60px_rgba(0,0,0,0.35)] transition-[width] duration-300 ease-out",
        isOpen ? "w-[16.75rem]" : "w-[4.75rem]",
      )}
    >
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,hsl(var(--primary)/0.24),transparent_28%),radial-gradient(circle_at_bottom_left,hsl(var(--primary)/0.12),transparent_24%),linear-gradient(180deg,rgba(255,255,255,0.035),rgba(255,255,255,0.01)_24%,rgba(0,0,0,0)_60%)]" />
      <div className="pointer-events-none absolute inset-0 opacity-[0.08] [background-image:radial-gradient(rgba(255,255,255,0.7)_0.7px,transparent_0.7px)] [background-size:18px_18px]" />
      <div className="pointer-events-none absolute inset-y-0 right-0 w-px bg-gradient-to-b from-transparent via-white/18 to-transparent" />

      <div className="relative z-10 flex h-full flex-col">
        <div className={cn("pb-2.5 pt-3", isOpen ? "px-3" : "px-2.5")}>
          <div className={cn("flex items-center", isOpen ? "justify-between gap-3" : "justify-center")}>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={isOpen ? handleNewChat : onToggle}
                  aria-label={isOpen ? "Go to chats home" : "Expand sidebar"}
                  className={cn(
                    "group relative flex shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-white/12",
                    "h-10 w-10 border-[hsl(var(--foreground)/0.1)] bg-[linear-gradient(145deg,hsl(var(--primary)/0.28),hsl(var(--primary)/0.14))]",
                    "shadow-[0_0_0_1px_rgba(255,255,255,0.03),0_12px_30px_hsl(var(--primary)/0.3)]",
                    "transition-all duration-300 ease-out hover:scale-[1.03] hover:shadow-[0_0_0_1px_rgba(255,255,255,0.05),0_16px_36px_hsl(var(--primary)/0.38)]",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--primary)/0.7)] focus-visible:ring-offset-2 focus-visible:ring-offset-[hsl(var(--sidebar-background))]",
                    "active:scale-[0.97]",
                  )}
                  >
                    <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_30%,rgba(255,255,255,0.32),transparent_38%)] opacity-80 transition-opacity duration-300 group-hover:opacity-100" />
                    <Sparkles className="relative h-4.5 w-4.5 text-white transition-transform duration-300 group-hover:scale-110 group-hover:rotate-6" />
                  </button>
              </TooltipTrigger>
              <TooltipContent side="right">{isOpen ? "All chats" : "Expand sidebar"}</TooltipContent>
            </Tooltip>

            {isOpen && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={onToggle}
                    aria-label="Collapse sidebar"
                    className={cn(
                      "ml-auto flex h-10 w-10 items-center justify-center rounded-xl text-[hsl(var(--muted-foreground))] transition-all duration-200",
                      "hover:bg-[hsl(var(--foreground)/0.06)] hover:text-[hsl(var(--foreground))]",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--primary)/0.5)] focus-visible:ring-offset-2 focus-visible:ring-offset-[hsl(var(--sidebar-background))]",
                    )}
                  >
                    <PanelLeftClose className="h-4.5 w-4.5" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="right">Collapse sidebar</TooltipContent>
              </Tooltip>
            )}
          </div>

          <div className={cn("mt-4", !isOpen && "flex justify-center")}>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={handleNewChat}
                  className={cn(
                    "group relative flex w-full items-center overflow-hidden rounded-full border",
                    "h-12 border-[hsl(var(--primary)/0.18)] bg-[linear-gradient(135deg,hsl(var(--primary)),hsl(var(--primary)/0.88)_45%,hsl(var(--primary)/0.72))] px-4 text-sm font-medium text-[hsl(var(--primary-foreground))]",
                    "shadow-[0_10px_28px_hsl(var(--primary)/0.34)] transition-all duration-300 ease-out",
                    "hover:-translate-y-0.5 hover:shadow-[0_14px_36px_hsl(var(--primary)/0.38)]",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--primary)/0.7)] focus-visible:ring-offset-2 focus-visible:ring-offset-[hsl(var(--sidebar-background))]",
                    "active:scale-[0.985]",
                    isOpen ? "justify-between" : "h-10 w-10 justify-center rounded-2xl px-0",
                  )}
                >
                  <div className="absolute inset-0 bg-[linear-gradient(120deg,transparent,rgba(255,255,255,0.12),transparent)] opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
                  <div className="flex items-center gap-2.5">
                    <span className="flex h-7 w-7 items-center justify-center rounded-full bg-white/14 shadow-inner shadow-white/10">
                      <Plus className="h-4 w-4 transition-transform duration-300 group-hover:rotate-90" />
                    </span>
                    {isOpen && <span>New Chat</span>}
                  </div>
                  {isOpen && (
                    <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[hsl(var(--primary-foreground)/0.8)]">
                      N
                    </span>
                  )}
                </button>
              </TooltipTrigger>
              {!isOpen && <TooltipContent side="right">New Chat</TooltipContent>}
            </Tooltip>
          </div>

          {isOpen && (
            <div className="mt-3.5">
              <div className="group relative">
                <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[hsl(var(--muted-foreground))] transition-colors duration-200 group-focus-within:text-[hsl(var(--primary))]" />
                <Input
                  type="text"
                  placeholder="Search chats"
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  className={cn(
                    "h-11 rounded-full border border-[hsl(var(--foreground)/0.1)] bg-[hsl(var(--foreground)/0.04)] pl-10 pr-10 text-sm text-[hsl(var(--foreground))] shadow-[inset_0_1px_0_hsl(var(--foreground)/0.04)]",
                    "placeholder:text-[hsl(var(--muted-foreground))] focus-visible:border-[hsl(var(--primary)/0.5)] focus-visible:ring-2 focus-visible:ring-[hsl(var(--primary)/0.25)]",
                  )}
                />
                {showSearchClear && (
                  <button
                    type="button"
                    onClick={() => setSearchQuery("")}
                    aria-label="Clear search"
                    className="absolute right-2.5 top-1/2 flex h-6.5 w-6.5 -translate-y-1/2 items-center justify-center rounded-full text-[hsl(var(--muted-foreground))] transition-all duration-200 hover:bg-[hsl(var(--foreground)/0.08)] hover:text-[hsl(var(--foreground))] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--primary)/0.5)]"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="px-3">
          <div className="h-px bg-gradient-to-r from-transparent via-[hsl(var(--foreground)/0.1)] to-transparent" />
        </div>

        <div
          className={cn(
            "sidebar-scrollbar group/chat-scroll relative flex-1 overflow-y-auto px-2.5 pb-2.5 pt-3.5 scroll-smooth",
          )}
        >
          {isOpen && (
            <div className="mb-3 flex items-center justify-between px-1">
              <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-[hsl(var(--muted-foreground))]">
                Conversations
              </p>
              <span className="rounded-full border border-[hsl(var(--foreground)/0.1)] bg-[hsl(var(--foreground)/0.04)] px-2 py-1 text-[10px] font-medium text-[hsl(var(--muted-foreground))]">
                {filteredChats.length}
              </span>
            </div>
          )}

          {isLoadingChats ? (
            <SidebarSkeleton isOpen={isOpen} />
          ) : filteredChats.length === 0 ? (
            <EmptyChats isOpen={isOpen} searchQuery={searchQuery} />
          ) : (
            <div className="space-y-1">
              {filteredChats.map((chat) => {
                const isActive = activeChat === chat.id;
                const collapsedLabel = chat.title || "Untitled Chat";

                const chatButton = (
                  <button
                    type="button"
                    onClick={() => handleProjectClick(chat.id)}
                    aria-current={isActive ? "page" : undefined}
                    title={isOpen ? chat.title : undefined}
                    className={cn(
                      "group/item relative flex w-full min-w-0 items-center gap-2.5 overflow-hidden rounded-2xl px-2.5 py-2 text-left transition-all duration-200 ease-out",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--primary)/0.5)] focus-visible:ring-offset-2 focus-visible:ring-offset-[hsl(var(--sidebar-background))]",
                      isOpen ? "min-h-[46px]" : "justify-center px-1.5",
                      isActive
                        ? "bg-[linear-gradient(90deg,hsl(var(--primary)/0.22),hsl(var(--primary)/0.1)_44%,transparent)] shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]"
                        : "bg-transparent hover:bg-[hsl(var(--foreground)/0.05)] hover:translate-x-1",
                    )}
                  >
                    <span
                      className={cn(
                        "absolute bottom-1.5 left-0 top-1.5 w-[3px] rounded-full transition-all duration-200",
                        isActive
                          ? "bg-[linear-gradient(180deg,hsl(var(--primary)),hsl(var(--primary)/0.7),hsl(var(--primary)))] shadow-[0_0_18px_hsl(var(--primary)/0.65)]"
                          : "bg-transparent group-hover/item:bg-[hsl(var(--primary)/0.3)]",
                      )}
                    />

                    <span
                      className={cn(
                        "flex h-8 w-8 shrink-0 items-center justify-center rounded-2xl text-[13px] font-semibold uppercase transition-all duration-200",
                        isActive
                          ? "bg-[hsl(var(--primary)/0.14)] text-[hsl(var(--primary-foreground))]"
                          : "bg-[hsl(var(--foreground)/0.05)] text-[hsl(var(--muted-foreground))] group-hover/item:bg-[hsl(var(--foreground)/0.08)] group-hover/item:text-[hsl(var(--foreground))]",
                      )}
                    >
                      {collapsedLabel.slice(0, 1).toUpperCase()}
                    </span>

                    {isOpen && (
                      <div className="min-w-0 flex-1">
                        <p
                          className={cn(
                            "truncate text-[14px] font-medium leading-5 transition-colors duration-200",
                            isActive
                              ? "text-[hsl(var(--foreground))]"
                              : "text-[hsl(var(--foreground)/0.78)] group-hover/item:text-[hsl(var(--foreground))]",
                          )}
                        >
                          {chat.title}
                        </p>
                      </div>
                    )}
                  </button>
                );

                return (
                  <div key={chat.id} className="group relative">
                    {isOpen ? (
                      <div className="flex items-center gap-2">
                        {chatButton}

                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <button
                              type="button"
                              aria-label={`More options for ${chat.title}`}
                              className={cn(
                                "flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-transparent text-[hsl(var(--muted-foreground))] transition-all duration-200",
                                "hover:bg-[hsl(var(--foreground)/0.06)] hover:text-[hsl(var(--foreground))]",
                                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--primary)/0.5)]",
                                "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100",
                              )}
                            >
                              <MoreHorizontal className="h-4 w-4" />
                            </button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent
                            align="end"
                            className="w-44 border-[hsl(var(--foreground)/0.1)] bg-[hsl(var(--popover)/0.98)] text-[hsl(var(--popover-foreground))] backdrop-blur-xl"
                          >
                            <DropdownMenuItem
                              className="cursor-pointer gap-2 text-[hsl(var(--popover-foreground))] focus:bg-[hsl(var(--primary)/0.18)] focus:text-[hsl(var(--foreground))]"
                              onSelect={() => openRename(chat)}
                            >
                              <Pencil className="h-4 w-4" />
                              Rename
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              className="cursor-pointer gap-2 text-[hsl(var(--popover-foreground))] focus:bg-[hsl(var(--primary)/0.18)] focus:text-[hsl(var(--foreground))]"
                              onSelect={() => openShare(chat)}
                            >
                              <Share2 className="h-4 w-4" />
                              Share
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              className="cursor-pointer gap-2 text-destructive focus:text-destructive"
                              onSelect={() => openDelete(chat)}
                            >
                              <Trash2 className="h-4 w-4" />
                              Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    ) : (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <div>{chatButton}</div>
                        </TooltipTrigger>
                        <TooltipContent side="right">{chat.title}</TooltipContent>
                      </Tooltip>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="px-3 pb-3">
          <div className="mb-3 h-px bg-gradient-to-r from-transparent via-[hsl(var(--foreground)/0.1)] to-transparent" />

          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={onSettingsClick}
                className={cn(
                  "group flex w-full items-center rounded-[20px] border border-[hsl(var(--foreground)/0.08)] bg-[hsl(var(--foreground)/0.035)] px-2.5 py-2.5 text-left transition-all duration-200 ease-out",
                  "shadow-[inset_0_1px_0_hsl(var(--foreground)/0.035)] backdrop-blur-xl hover:border-[hsl(var(--foreground)/0.12)] hover:bg-[hsl(var(--foreground)/0.055)]",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--primary)/0.5)] focus-visible:ring-offset-2 focus-visible:ring-offset-[hsl(var(--sidebar-background))]",
                  isOpen ? "gap-3" : "justify-center px-0",
                )}
              >
                <span className="flex h-8.5 w-8.5 shrink-0 items-center justify-center rounded-2xl border border-[hsl(var(--foreground)/0.1)] bg-[hsl(var(--foreground)/0.04)] text-[hsl(var(--muted-foreground))] transition-all duration-300 group-hover:rotate-45 group-hover:text-[hsl(var(--foreground))]">
                  <Settings className="h-3.5 w-3.5" />
                </span>
                {isOpen && (
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-[hsl(var(--foreground))]">Settings</p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Preferences and account</p>
                  </div>
                )}
              </button>
            </TooltipTrigger>
            {!isOpen && <TooltipContent side="right">Settings</TooltipContent>}
          </Tooltip>
        </div>
      </div>

      <Dialog open={!!renameTarget} onOpenChange={(open) => !open && setRenameTarget(null)}>
        <DialogContent className="z-[110] overflow-hidden border-white/10 bg-[#101119]/95 text-zinc-100 backdrop-blur-xl sm:max-w-md">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,hsl(var(--primary)/0.22),transparent_42%),linear-gradient(180deg,rgba(255,255,255,0.04),transparent_38%)]" />
          <DialogHeader>
            <div className="relative mb-1 flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-[hsl(var(--primary)/0.18)] bg-[linear-gradient(135deg,hsl(var(--primary)/0.24),hsl(var(--primary)/0.12))] shadow-[0_12px_30px_hsl(var(--primary)/0.24)]">
                <Pencil className="h-4 w-4 text-white" />
              </div>
              <div>
                <DialogTitle className="text-xl text-white">Rename chat</DialogTitle>
                <DialogDescription className="mt-1 text-zinc-400">
                  Give this conversation a sharper, cleaner identity in your workspace.
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
              placeholder="Chat name"
              onKeyDown={(event) => event.key === "Enter" && submitRename()}
              className="h-12 rounded-2xl border-white/10 bg-[hsl(var(--background)/0.78)] text-base text-zinc-100 placeholder:text-zinc-500"
            />
            <div className="mt-3 flex items-center justify-between text-xs text-zinc-500">
              <span className="truncate">Visible in your sidebar and shared views</span>
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

      <Dialog open={!!shareTarget} onOpenChange={(open) => !open && setShareTarget(null)}>
        <DialogContent className="z-[110] overflow-hidden border-white/10 bg-[#101119]/95 text-zinc-100 backdrop-blur-xl sm:max-w-lg">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,hsl(var(--primary)/0.22),transparent_40%),radial-gradient(circle_at_bottom_right,hsl(var(--primary)/0.14),transparent_30%)]" />
          <DialogHeader>
            <div className="relative flex items-start gap-3">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-[hsl(var(--primary)/0.18)] bg-[linear-gradient(135deg,hsl(var(--primary)/0.24),hsl(var(--primary)/0.12))] shadow-[0_12px_30px_hsl(var(--primary)/0.24)]">
                <Share2 className="h-5 w-5 text-white" />
              </div>
              <div className="min-w-0">
                <DialogTitle className="text-xl text-white">Share chat</DialogTitle>
                <DialogDescription className="mt-1 text-zinc-400">
                  Turn this conversation into a polished shareable moment for your team or clients.
                </DialogDescription>
              </div>
            </div>
          </DialogHeader>
          <div className="relative mt-2 overflow-hidden rounded-[28px] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.06),rgba(255,255,255,0.025))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,hsl(var(--primary)/0.16),transparent_45%)]" />
            <div className="relative">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-white">
                    {shareTarget?.title || "CODEXA chat"}
                  </p>
                  <p className="mt-1 text-xs text-zinc-400">Private link for this conversation</p>
                </div>
                <div className="rounded-full border border-[hsl(var(--primary)/0.22)] bg-[hsl(var(--primary)/0.12)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-[hsl(var(--primary))]">
                  Live
                </div>
              </div>

              <div className="flex gap-2">
                <Input
                  readOnly
                  value={shareUrl}
                  className="h-12 border-white/10 bg-[hsl(var(--background)/0.78)] font-mono text-xs text-zinc-100"
                />
                <Button
                  type="button"
                  variant="secondary"
                  size="icon"
                  className="h-12 w-12 shrink-0 rounded-2xl border border-[hsl(var(--primary)/0.16)] bg-[hsl(var(--primary)/0.08)]"
                  onClick={() => copyShareLink(shareUrl)}
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </div>
          <Button
            type="button"
            className="w-full rounded-2xl bg-[linear-gradient(135deg,hsl(var(--primary)),hsl(var(--primary)/0.88)_50%,hsl(var(--primary)/0.72))] py-6 text-[hsl(var(--primary-foreground))] shadow-[0_14px_34px_hsl(var(--primary)/0.3)] hover:opacity-95"
            onClick={() => copyShareLink(shareUrl)}
          >
            <Copy className="mr-2 h-4 w-4" />
            Copy link
          </Button>
          <Separator className="bg-white/10" />
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-zinc-100">Share everywhere</p>
            <p className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">Fast actions</p>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <ShareOptionButton
              label="WhatsApp"
              icon={<MessageCircle className="h-5 w-5 text-emerald-400" />}
              onClick={() => openExternalShare("whatsapp")}
            />
            <ShareOptionButton
              label="Telegram"
              icon={<Send className="h-5 w-5 text-sky-400" />}
              onClick={() => openExternalShare("telegram")}
            />
            <ShareOptionButton
              label="Email"
              icon={<Mail className="h-5 w-5 text-zinc-100" />}
              onClick={() => openExternalShare("email")}
            />
            <ShareOptionButton
              label="X"
              icon={<span className="text-sm font-bold leading-none text-white">X</span>}
              onClick={() => openExternalShare("twitter")}
            />
            <ShareOptionButton
              label="LinkedIn"
              icon={<Linkedin className="h-5 w-5 text-blue-400" />}
              onClick={() => openExternalShare("linkedin")}
            />
            <ShareOptionButton
              label="Facebook"
              icon={<Facebook className="h-5 w-5 text-blue-400" />}
              onClick={() => openExternalShare("facebook")}
            />
          </div>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent className="z-[110] border-white/10 bg-[#101119]/95 text-zinc-100 backdrop-blur-xl">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete chat?</AlertDialogTitle>
            <AlertDialogDescription className="text-zinc-400">
              This will permanently remove "{deleteTarget?.title}", its messages, and any
              generated projects and files linked to it. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteBusy}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={(event) => {
                event.preventDefault();
                submitDelete();
              }}
              disabled={deleteBusy}
            >
              {deleteBusy ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </aside>
  );
}
