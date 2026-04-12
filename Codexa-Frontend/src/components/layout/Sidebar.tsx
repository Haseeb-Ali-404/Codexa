import { useState, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/utils";
import { API_BASE } from "@/lib/api";
import { useNavigate, useParams } from "react-router-dom";
import {
  Plus,
  Settings,
  Sparkles,
  Search,
  MoreHorizontal,
  Pencil,
  Share2,
  Trash2,
  Copy,
  MessageCircle,
  Mail,
  Send,
  Linkedin,
  Facebook,
} from "lucide-react";
import { useAppData } from "@/context/useAppData";
import ChatLoader from "../ui/loader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
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

export function Sidebar({ isOpen, onToggle, onSettingsClick }: SidebarProps) {
  const { userId } = useAuth();
  const { userChats, refreshData } = useAppData();
  const navigate = useNavigate();
  const [chats, setChats] = useState<Chat[]>([]);
  const [activeChat, setActiveChat] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const { chatId } = useParams();

  const [renameTarget, setRenameTarget] = useState<Chat | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameBusy, setRenameBusy] = useState(false);

  const [shareTarget, setShareTarget] = useState<Chat | null>(null);

  const [deleteTarget, setDeleteTarget] = useState<Chat | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  useEffect(() => {
    if (!userId) return;

    const formatted = userChats.map((p: { _id?: string; id?: string; title?: string }) => ({
      id: p._id || p.id || "",
      title: p.title || "Untitled Project",
    }));

    setChats(formatted);

    setActiveChat(chatId || "");
  }, [userId, chatId, userChats]);

  useEffect(() => {
    if (renameTarget) setRenameValue(renameTarget.title);
  }, [renameTarget]);

  const handleProjectClick = (chatID: string) => {
    navigate(`/c/${chatID}`);
    setActiveChat(chatID);
  };

  const handleNewChat = () => {
    navigate("/");
    setActiveChat("");
  };

  const filteredChats = chats.filter((c) =>
    c.title.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  const openRename = (chat: Chat) => {
    setTimeout(() => setRenameTarget(chat), 0);
  };

  const openShare = (chat: Chat) => {
    setTimeout(() => setShareTarget(chat), 0);
  };

  const openDelete = (chat: Chat) => {
    setTimeout(() => setDeleteTarget(chat), 0);
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
      const res = await fetch(`${API_BASE}/chat/${renameTarget.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, title }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.detail || "Rename failed");
      }
      toast.success("Chat renamed");
      setRenameTarget(null);
      refreshData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Rename failed");
    } finally {
      setRenameBusy(false);
    }
  };

  const submitDelete = async () => {
    if (!userId || !deleteTarget) return;
    setDeleteBusy(true);
    try {
      const res = await fetch(
        `${API_BASE}/chat/${deleteTarget.id}?user_id=${encodeURIComponent(userId)}`,
        { method: "DELETE" },
      );
      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.detail || "Delete failed");
      }
      toast.success("Chat deleted");
      if (activeChat === deleteTarget.id) {
        navigate("/");
        setActiveChat("");
      }
      setDeleteTarget(null);
      refreshData();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
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
    const u = urls[kind];
    if (u) window.open(u, "_blank", "noopener,noreferrer");
  };

  return (
    <aside
      className={cn(
        "h-full border-r border-border/70 dark:border-white/10 bg-background/80 dark:bg-[#0f1115]/85 backdrop-blur-xl flex flex-col transition-all duration-300 ease-out relative",
        isOpen ? "w-64" : "w-16",
      )}
    >
      <div className="absolute inset-0 bg-gradient-to-b from-primary/[0.04] dark:from-white/[0.03] via-transparent to-transparent pointer-events-none" />

      <div className="p-3 relative z-10 space-y-3">
        <div
          className={cn(
            "flex items-center gap-2",
            isOpen ? "justify-between" : "justify-center",
          )}
        >
          <button
            type="button"
            onClick={onToggle}
            className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary to-accent flex items-center justify-center shadow-sm shadow-primary/20 hover:brightness-110 transition-all duration-200 cursor-pointer"
          >
            <Sparkles className="w-4 h-4 text-white" />
          </button>
          {isOpen && (
            <div className="flex-1 min-w-0">
              <span className="text-sm font-semibold text-foreground block">
                CODEXA
              </span>
              <span className="text-[10px] text-muted-foreground block">Chats</span>
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={handleNewChat}
          className={cn(
            "w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl",
            "bg-gradient-to-r from-primary to-primary/85 text-primary-foreground",
            "text-sm font-medium transition-all duration-200 hover:brightness-110 hover:shadow-md hover:shadow-primary/20",
            !isOpen && "px-0",
          )}
        >
          <Plus className="w-4 h-4" />
          {isOpen && <span>New Chat</span>}
        </button>

        {isOpen && (
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search chats..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-2 rounded-xl bg-muted/40 dark:bg-white/[0.04] border border-border/80 dark:border-white/10 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary/50 transition-all"
            />
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin px-3 py-3 relative z-10">
        <div className="space-y-1.5">
          {filteredChats.length === 0 && <ChatLoader />}
          {filteredChats.map((chat) => (
            <div
              key={chat.id}
              className={cn(
                "group flex items-center gap-0.5 rounded-lg border transition-all duration-200",
                activeChat === chat.id
                  ? "bg-primary/12 border-primary/25 shadow-sm ring-1 ring-primary/15 dark:bg-primary/15 dark:border-primary/30"
                  : "border-transparent hover:bg-muted/60 dark:hover:bg-white/[0.06]",
              )}
            >
              <button
                type="button"
                onClick={() => {
                  setActiveChat(chat.id);
                  handleProjectClick(chat.id);
                }}
                className={cn(
                  "flex-1 min-w-0 text-left px-3 py-2.5 rounded-lg",
                  activeChat === chat.id
                    ? "text-foreground font-medium"
                    : "text-muted-foreground hover:text-foreground",
                  !isOpen && "text-center px-1.5",
                )}
                title={chat.title}
              >
                {isOpen && (
                  <span
                    className={cn(
                      "text-sm truncate block",
                      activeChat === chat.id && "text-foreground",
                    )}
                  >
                    {chat.title}
                  </span>
                )}
                {!isOpen && (
                  <span
                    className={cn(
                      "text-xs font-semibold",
                      activeChat === chat.id
                        ? "text-primary"
                        : "text-muted-foreground",
                    )}
                  >
                    {chat.title.slice(0, 1).toUpperCase()}
                  </span>
                )}
              </button>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    aria-label="Chat options"
                    onClick={(e) => e.stopPropagation()}
                    className={cn(
                      "shrink-0 rounded-md p-1.5 text-muted-foreground hover:text-foreground hover:bg-background/80 dark:hover:bg-white/10 transition-opacity",
                      isOpen ? "opacity-0 group-hover:opacity-100" : "opacity-100",
                    )}
                  >
                    <MoreHorizontal className="w-4 h-4" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48 z-[100]">
                  <DropdownMenuItem
                    className="gap-2 cursor-pointer"
                    onSelect={() => openRename(chat)}
                  >
                    <Pencil className="w-4 h-4" />
                    Rename
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    className="gap-2 cursor-pointer"
                    onSelect={() => openShare(chat)}
                  >
                    <Share2 className="w-4 h-4" />
                    Share
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    className="gap-2 cursor-pointer text-destructive focus:text-destructive"
                    onSelect={() => openDelete(chat)}
                  >
                    <Trash2 className="w-4 h-4" />
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          ))}
        </div>
      </div>

      <div className="p-3 border-t border-border/70 dark:border-white/10/70 relative z-10 mt-1">
        <button
          type="button"
          onClick={onSettingsClick}
          className={cn(
            "w-full flex items-center gap-2 px-3 py-2.5 rounded-lg",
            "text-muted-foreground hover:text-foreground hover:bg-white/[0.06] transition-all duration-200",
            !isOpen && "justify-center px-0",
          )}
        >
          <Settings className="w-4 h-4" />
          {isOpen && <span className="text-sm">Settings</span>}
        </button>
      </div>

      {/* Rename */}
      <Dialog open={!!renameTarget} onOpenChange={(o) => !o && setRenameTarget(null)}>
        <DialogContent className="sm:max-w-md z-[110]">
          <DialogHeader>
            <DialogTitle>Rename chat</DialogTitle>
            <DialogDescription>Update the name shown in your sidebar.</DialogDescription>
          </DialogHeader>
          <Input
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            placeholder="Chat name"
            onKeyDown={(e) => e.key === "Enter" && submitRename()}
          />
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" onClick={() => setRenameTarget(null)}>
              Cancel
            </Button>
            <Button onClick={submitRename} disabled={renameBusy}>
              {renameBusy ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Share (ChatGPT-style) */}
      <Dialog open={!!shareTarget} onOpenChange={(o) => !o && setShareTarget(null)}>
        <DialogContent className="sm:max-w-md z-[110]">
          <DialogHeader>
            <DialogTitle>Share chat</DialogTitle>
            <DialogDescription>
              Copy a link to this chat or share it through your favorite app. Recipients may need
              to sign in to CODEXA to open it.
            </DialogDescription>
          </DialogHeader>
          <div className="flex gap-2">
            <Input readOnly value={shareUrl} className="font-mono text-xs" />
            <Button
              type="button"
              variant="secondary"
              size="icon"
              className="shrink-0"
              onClick={() => copyShareLink(shareUrl)}
            >
              <Copy className="w-4 h-4" />
            </Button>
          </div>
          <Button type="button" className="w-full" onClick={() => copyShareLink(shareUrl)}>
            <Copy className="w-4 h-4 mr-2" />
            Copy link
          </Button>
          <Separator />
          <p className="text-sm font-medium text-foreground">Share via</p>
          <div className="grid grid-cols-3 gap-2">
            <Button
              type="button"
              variant="outline"
              className="h-auto py-3 flex flex-col gap-1 text-xs"
              onClick={() => openExternalShare("whatsapp")}
            >
              <MessageCircle className="w-5 h-5 text-emerald-600" />
              WhatsApp
            </Button>
            <Button
              type="button"
              variant="outline"
              className="h-auto py-3 flex flex-col gap-1 text-xs"
              onClick={() => openExternalShare("telegram")}
            >
              <Send className="w-5 h-5 text-sky-500" />
              Telegram
            </Button>
            <Button
              type="button"
              variant="outline"
              className="h-auto py-3 flex flex-col gap-1 text-xs"
              onClick={() => openExternalShare("email")}
            >
              <Mail className="w-5 h-5" />
              Email
            </Button>
            <Button
              type="button"
              variant="outline"
              className="h-auto py-3 flex flex-col gap-1 text-xs"
              onClick={() => openExternalShare("twitter")}
            >
              <span className="text-sm font-bold leading-none">𝕏</span>
              X
            </Button>
            <Button
              type="button"
              variant="outline"
              className="h-auto py-3 flex flex-col gap-1 text-xs"
              onClick={() => openExternalShare("linkedin")}
            >
              <Linkedin className="w-5 h-5 text-blue-600" />
              LinkedIn
            </Button>
            <Button
              type="button"
              variant="outline"
              className="h-auto py-3 flex flex-col gap-1 text-xs"
              onClick={() => openExternalShare("facebook")}
            >
              <Facebook className="w-5 h-5 text-blue-600" />
              Facebook
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <AlertDialogContent className="z-[110]">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete chat?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently remove “{deleteTarget?.title}”, its messages, and any
              generated projects and files linked to it. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteBusy}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={(e) => {
                e.preventDefault();
                submitDelete();
              }}
              disabled={deleteBusy}
            >
              {deleteBusy ? "Deleting…" : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </aside>
  );
}
