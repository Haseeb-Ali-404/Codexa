import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import { GlassCard } from "@/components/ui/GlassCard";
import {
  SettingsPillSwitch,
  PillOptionGroup,
  PillOption,
  SettingsPillRow,
  PillSelectRow,
} from "./SettingsPillControls";
import { useAuth } from "@/context/AuthContext";
import {
  X,
  User,
  Palette,
  Bell,
  Shield,
  Keyboard,
  Globe,
  Zap,
  ChevronRight,
  Moon,
  Sun,
  Monitor,
  Mail,
  Camera,
  Trash2,
  Download,
  Eye,
  EyeOff,
  Smartphone,
  History,
  Sparkles,
  RotateCcw,
} from "lucide-react";
import { toast } from "sonner";

interface SettingsPanelProps {
  isOpen: boolean;
  onClose: () => void;
  isDark: boolean;
  onThemeChange: (isDark: boolean) => void;
}

type SettingsTab =
  | "account"
  | "appearance"
  | "notifications"
  | "privacy"
  | "shortcuts"
  | "language"
  | "ai";
type ThemeType = "light" | "dark" | "original" | "gray";

const tabs = [
  { id: "account" as SettingsTab, label: "Account", icon: User },
  { id: "appearance" as SettingsTab, label: "Appearance", icon: Palette },
  { id: "notifications" as SettingsTab, label: "Notifications", icon: Bell },
  { id: "privacy" as SettingsTab, label: "Privacy & Security", icon: Shield },
  {
    id: "shortcuts" as SettingsTab,
    label: "Keyboard Shortcuts",
    icon: Keyboard,
  },
  { id: "language" as SettingsTab, label: "Language", icon: Globe },
  { id: "ai" as SettingsTab, label: "AI Settings", icon: Zap },
];

const accentColors = [
  {
    name: "Cyan",
    hue: "187",
    saturation: "100%",
    lightness: "42%",
    darkLightness: "35%",
    isTransparent: false,
  },
  {
    name: "Blue",
    hue: "217",
    saturation: "91%",
    lightness: "60%",
    darkLightness: "50%",
    isTransparent: false,
  },
  {
    name: "Violet",
    hue: "262",
    saturation: "80%",
    lightness: "60%",
    darkLightness: "55%",
    isTransparent: false,
  },
  {
    name: "Pink",
    hue: "330",
    saturation: "81%",
    lightness: "60%",
    darkLightness: "55%",
    isTransparent: false,
  },
  {
    name: "Emerald",
    hue: "160",
    saturation: "84%",
    lightness: "39%",
    darkLightness: "35%",
    isTransparent: false,
  },
  {
    name: "Amber",
    hue: "38",
    saturation: "92%",
    lightness: "50%",
    darkLightness: "45%",
    isTransparent: false,
  },
  {
    name: "Rose",
    hue: "350",
    saturation: "89%",
    lightness: "60%",
    darkLightness: "55%",
    isTransparent: false,
  },
  {
    name: "Transparent",
    hue: "0",
    saturation: "0%",
    lightness: "100%",
    darkLightness: "100%",
    isTransparent: true,
  },
  {
    name: "Custom",
    hue: "217",
    saturation: "91%",
    lightness: "60%",
    darkLightness: "55%",
    isTransparent: false,
    isCustom: true,
  },
];

const CUSTOM_ACCENT_INDEX = accentColors.length - 1;

/**
 * shadcn/Radix menus & ghost buttons use `bg-accent` for hover, not `bg-primary`.
 * Theme settings only updated `--primary`, so hovers stayed the default purple `--accent`.
 */
function syncAccentToPrimary(
  root: HTMLElement,
  primaryHsl: string,
  accentForeground: string,
) {
  root.style.setProperty("--accent", primaryHsl);
  root.style.setProperty("--accent-foreground", accentForeground);
  root.style.setProperty("--gradient-end", primaryHsl);
  root.style.setProperty("--glow-accent", primaryHsl);
}

const languages = [
  { code: "en", name: "English", flag: "🇺🇸" },
  { code: "es", name: "Español", flag: "🇪🇸" },
  { code: "fr", name: "Français", flag: "🇫🇷" },
  { code: "de", name: "Deutsch", flag: "🇩🇪" },
  { code: "ja", name: "日本語", flag: "🇯🇵" },
  { code: "zh", name: "中文", flag: "🇨🇳" },
];

const shortcuts = [
  { action: "New Chat", keys: ["⌘", "N"] },
  { action: "Search", keys: ["⌘", "K"] },
  { action: "Toggle Sidebar", keys: ["⌘", "B"] },
  { action: "Toggle Preview", keys: ["⌘", "P"] },
  { action: "Toggle Code", keys: ["⌘", "E"] },
  { action: "Settings", keys: ["⌘", ","] },
  { action: "Close Panel", keys: ["Esc"] },
  { action: "Send Message", keys: ["Enter"] },
  { action: "New Line", keys: ["Shift", "Enter"] },
];

// Helper to load settings from localStorage
const loadSetting = <T,>(key: string, defaultValue: T): T => {
  try {
    const saved = localStorage.getItem(`nexus-${key}`);
    return saved ? JSON.parse(saved) : defaultValue;
  } catch {
    return defaultValue;
  }
};

// Helper to save settings to localStorage
const saveSetting = (key: string, value: unknown) => {
  localStorage.setItem(`nexus-${key}`, JSON.stringify(value));
};

export function SettingsPanel({
  isOpen,
  onClose,
  isDark,
  onThemeChange,
}: SettingsPanelProps) {
  const [activeTab, setActiveTab] = useState<SettingsTab>("appearance");
  const [theme, setTheme] = useState<ThemeType>(() =>
    loadSetting("theme", isDark ? "dark" : "light")
  );
  const [selectedModel, setSelectedModel] = useState(() =>
    loadSetting("model", 0)
  );
  const [responseStyle, setResponseStyle] = useState(() =>
    loadSetting("response-style", 1)
  );
  const [selectedAccent, setSelectedAccent] = useState(() =>
    loadSetting("accent-color", 0)
  );
  const [fontSize, setFontSize] = useState(() => loadSetting("font-size", 16));
  const [animationsEnabled, setAnimationsEnabled] = useState(() =>
    loadSetting("animations", true)
  );
  const [notificationsEnabled, setNotificationsEnabled] = useState(() =>
    loadSetting("notifications", true)
  );
  const [soundEnabled, setSoundEnabled] = useState(() =>
    loadSetting("sound", true)
  );
  const [emailNotifications, setEmailNotifications] = useState(() =>
    loadSetting("email-notifications", true)
  );
  const [selectedLanguage, setSelectedLanguage] = useState(() =>
    loadSetting("language", "en")
  );
  const [showPassword, setShowPassword] = useState(false);
  const [twoFactorEnabled, setTwoFactorEnabled] = useState(() =>
    loadSetting("2fa", false)
  );
  const [dataCollection, setDataCollection] = useState(() =>
    loadSetting("data-collection", true)
  );
  const [codeFormatting, setCodeFormatting] = useState(() =>
    loadSetting("code-formatting", true)
  );
  const [streamingEnabled, setStreamingEnabled] = useState(() =>
    loadSetting("streaming", true)
  );
  const [compactMode, setCompactMode] = useState(() =>
    loadSetting("compact-mode", false)
  );
  const [autoSave, setAutoSave] = useState(() =>
    loadSetting("auto-save", true)
  );
  const [customColor, setCustomColor] = useState(() =>
    loadSetting("custom-color", "#3b82f6")
  );

  const { user } = useAuth();

  // Apply accent color to CSS variables
  useEffect(() => {
    const color = accentColors[selectedAccent];
    const root = document.documentElement;

    if (color.isCustom) {
      applyCustomAccentColor(customColor);
    } else if (color.isTransparent) {
      // Transparent accent - use muted foreground color
      const ph = "215 20% 55%";
      root.style.setProperty("--primary", ph);
      root.style.setProperty("--ring", ph);
      root.style.setProperty("--glow-primary", ph);
      root.style.setProperty("--gradient-start", ph);
      syncAccentToPrimary(root, "222 30% 18%", "210 40% 98%");
    } else {
      // Set primary color based on theme
      if (
        isDark ||
        theme === "dark" ||
        theme === "original" ||
        theme === "gray"
      ) {
        const ph = `${color.hue} ${color.saturation} ${color.lightness}`;
        root.style.setProperty("--primary", ph);
        root.style.setProperty("--ring", ph);
        root.style.setProperty("--glow-primary", ph);
        root.style.setProperty("--gradient-start", ph);
        syncAccentToPrimary(root, ph, "222 47% 6%");
      } else {
        const ph = `${color.hue} ${color.saturation} ${color.darkLightness}`;
        root.style.setProperty("--primary", ph);
        root.style.setProperty("--ring", ph);
        root.style.setProperty("--glow-primary", ph);
        root.style.setProperty("--gradient-start", ph);
        syncAccentToPrimary(root, ph, "0 0% 100%");
      }
    }
    saveSetting("accent-color", selectedAccent);
  }, [selectedAccent, isDark, theme, customColor]);

  // Apply font size as CSS variable and persist
  useEffect(() => {
    document.documentElement.style.setProperty(
      "--user-font-size",
      `${fontSize}px`
    );
    saveSetting("font-size", fontSize);
  }, [fontSize]);

  // Apply animations setting
  useEffect(() => {
    if (animationsEnabled) {
      document.documentElement.classList.remove("reduce-motion");
    } else {
      document.documentElement.classList.add("reduce-motion");
    }
    saveSetting("animations", animationsEnabled);
  }, [animationsEnabled]);

  // Persist other settings
  useEffect(() => {
    saveSetting("theme", theme);
  }, [theme]);
  useEffect(() => {
    saveSetting("model", selectedModel);
  }, [selectedModel]);
  useEffect(() => {
    saveSetting("response-style", responseStyle);
  }, [responseStyle]);
  useEffect(() => {
    saveSetting("notifications", notificationsEnabled);
  }, [notificationsEnabled]);
  useEffect(() => {
    saveSetting("sound", soundEnabled);
  }, [soundEnabled]);
  useEffect(() => {
    saveSetting("email-notifications", emailNotifications);
  }, [emailNotifications]);
  useEffect(() => {
    saveSetting("language", selectedLanguage);
  }, [selectedLanguage]);
  useEffect(() => {
    saveSetting("2fa", twoFactorEnabled);
  }, [twoFactorEnabled]);
  useEffect(() => {
    saveSetting("data-collection", dataCollection);
  }, [dataCollection]);
  useEffect(() => {
    saveSetting("code-formatting", codeFormatting);
  }, [codeFormatting]);
  useEffect(() => {
    saveSetting("streaming", streamingEnabled);
  }, [streamingEnabled]);
  useEffect(() => {
    saveSetting("compact-mode", compactMode);
  }, [compactMode]);
  useEffect(() => {
    saveSetting("auto-save", autoSave);
  }, [autoSave]);
  useEffect(() => {
    saveSetting("custom-color", customColor);
  }, [customColor]);

  // Helper function to apply custom accent color
  const applyCustomAccentColor = (color: string) => {
    const root = document.documentElement;
    // Convert hex to HSL
    const hex = color.replace("#", "");
    const r = parseInt(hex.substr(0, 2), 16) / 255;
    const g = parseInt(hex.substr(2, 2), 16) / 255;
    const b = parseInt(hex.substr(4, 2), 16) / 255;

    const max = Math.max(r, g, b),
      min = Math.min(r, g, b);
    let h = 0,
      s = 0;
    const l = (max + min) / 2;

    if (max !== min) {
      const d = max - min;
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      switch (max) {
        case r:
          h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
          break;
        case g:
          h = ((b - r) / d + 2) / 6;
          break;
        case b:
          h = ((r - g) / d + 4) / 6;
          break;
      }
    }

    const hue = Math.round(h * 360);
    const sat = Math.round(s * 100);
    const light = Math.round(l * 100);

    const ph = `${hue} ${sat}% ${light}%`;
    root.style.setProperty("--custom-primary", ph);
    root.style.setProperty("--primary", ph);
    root.style.setProperty("--ring", ph);
    root.style.setProperty("--glow-primary", ph);
    root.style.setProperty("--gradient-start", ph);
    const accentFg = light > 48 ? "222 47% 11%" : "210 40% 98%";
    syncAccentToPrimary(root, ph, accentFg);
  };

  if (!isOpen) return null;

  const handleThemeChange = (newTheme: ThemeType) => {
    setTheme(newTheme);
    const root = document.documentElement;

    // Remove all theme classes
    root.classList.remove("light", "dark", "original", "gray", "custom");

    if (newTheme === "light") {
      root.classList.add("light");
      onThemeChange(false);
    } else if (newTheme === "dark") {
      root.classList.add("dark");
      onThemeChange(true);
    } else if (newTheme === "original") {
      // Original is the default root theme (no class needed)
      onThemeChange(true);
    } else if (newTheme === "gray") {
      root.classList.add("gray");
      onThemeChange(true);
    }
    toast.success(`Theme changed to ${newTheme}`);
  };

  const handleCustomColorChange = (color: string) => {
    setCustomColor(color);
    if (selectedAccent === CUSTOM_ACCENT_INDEX) {
      applyCustomAccentColor(color);
    }
  };

  const handleAccentChange = (index: number) => {
    setSelectedAccent(index);
    toast.success(`Accent color changed to ${accentColors[index].name}`);
  };

  const handleFontSizeChange = (value: number) => {
    const clampedValue = Math.min(24, Math.max(12, value));
    setFontSize(clampedValue);
  };

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    handleFontSizeChange(parseInt(e.target.value));
  };

  const handleResetSettings = () => {
    setFontSize(16);
    setSelectedAccent(0);
    setAnimationsEnabled(true);
    setCompactMode(false);
    toast.success("Appearance settings reset to defaults");
  };

  const handleModelChange = (index: number) => {
    setSelectedModel(index);
    const modelNames = ["CODEXA Pro", "CODEXA Fast", "CODEXA Light"];
    toast.success(`Switched to ${modelNames[index]}`);
  };

  const handleResponseStyleChange = (index: number) => {
    setResponseStyle(index);
    const styles = ["Concise", "Balanced", "Detailed"];
    toast.success(`Response style set to ${styles[index]}`);
  };

  const getAccentColorClass = (index: number) => {
    const colors = [
      "bg-cyan-500",
      "bg-blue-500",
      "bg-violet-500",
      "bg-pink-500",
      "bg-emerald-500",
      "bg-amber-500",
      "bg-rose-500",
      "bg-gradient-to-br from-gray-200 to-gray-400 dark:from-gray-600 dark:to-gray-800",
      "bg-gradient-to-br from-sky-500 to-indigo-500",
    ];
    return colors[index];
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/35 dark:bg-black/55 backdrop-blur-sm animate-fade-in-up"
        onClick={onClose}
      />

      {/* Panel */}
      <GlassCard
        variant="strong"
        className="relative w-full max-w-5xl h-[82vh] max-h-[760px] flex flex-col overflow-hidden animate-fade-in-scale rounded-2xl border border-border/70 shadow-2xl shadow-black/20 dark:shadow-black/40 bg-background/95 dark:bg-card/90 backdrop-blur-xl"
      >
        {/* Header */}
        <div className="h-14 px-5 border-b border-border/60 bg-background/85 dark:bg-card/70 backdrop-blur-md flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-foreground">Settings</h2>
            <p className="text-[11px] text-muted-foreground">Manage your account and workspace preferences</p>
          </div>
        </div>

        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-3 right-3 p-2 rounded-lg hover:bg-secondary/70 text-muted-foreground hover:text-foreground transition-all duration-200 z-10"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex min-h-0 flex-1">
          {/* Sidebar */}
          <aside className="w-64 border-r border-border/60 p-3 bg-secondary/25 dark:bg-secondary/15">
            <nav className="space-y-1.5">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    "w-full flex items-center gap-3 px-3.5 py-2.5 rounded-full text-sm font-medium transition-all duration-200",
                    activeTab === tab.id
                      ? "bg-primary text-primary-foreground shadow-md shadow-primary/25"
                      : "text-muted-foreground hover:text-foreground hover:bg-background/55 dark:hover:bg-white/[0.06]"
                  )}
                >
                  <tab.icon className="w-4 h-4 shrink-0" />
                  <span className="text-left truncate">{tab.label}</span>
                  {activeTab === tab.id && (
                    <ChevronRight className="w-4 h-4 ml-auto shrink-0 opacity-90" />
                  )}
                </button>
              ))}
            </nav>
          </aside>

          {/* Content */}
          <div className="flex-1 p-6 overflow-y-auto scrollbar-thin">
          {/* Account Tab */}
          {activeTab === "account" && (
            <div className="space-y-8 animate-fade-in-up">
              <div>
                <h3 className="text-xl font-semibold text-foreground mb-2">
                  Account
                </h3>
                <p className="text-sm text-muted-foreground">
                  Manage your account information and preferences.
                </p>
              </div>

              {/* Profile Section */}
              <div className="space-y-4">
                <h4 className="text-sm font-medium text-foreground">Profile</h4>
                <div className="flex items-start gap-6 p-4 rounded-2xl border border-border/50 bg-secondary/20 dark:bg-white/[0.04]">
                  <div className="relative group">
                    <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-violet-500 via-purple-500 to-fuchsia-500 flex items-center justify-center text-2xl font-bold text-white shadow-lg">
                      {user?.name
                        ? user.name
                            .split(/\s+/)
                            .map((n) => n[0])
                            .join("")
                            .slice(0, 2)
                            .toUpperCase()
                        : "U"}
                    </div>
                    <button className="absolute inset-0 rounded-2xl bg-background/80 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                      <Camera className="w-6 h-6 text-foreground" />
                    </button>
                  </div>
                  <div className="flex-1 space-y-3">
                    <div>
                      <label className="text-xs text-muted-foreground">
                        Display Name
                      </label>
                      <input
                        type="text"
                        defaultValue={user?.name ?? "User Name"}
                        className="w-full mt-1 px-3 py-2 rounded-full bg-background border border-border/50 text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-muted-foreground">
                        Email
                      </label>
                      <div className="flex items-center gap-2 mt-1">
                        <input
                          type="email"
                          defaultValue={user?.email ?? "example@email.com"}
                          className="flex-1 px-3 py-2 rounded-full bg-background border border-border/50 text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                        />
                        <Mail className="w-4 h-4 text-muted-foreground" />
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Password Section */}
              <div className="space-y-4">
                <h4 className="text-sm font-medium text-foreground">
                  Change Password
                </h4>
                <div className="space-y-3 p-4 rounded-2xl border border-border/50 bg-secondary/20 dark:bg-white/[0.04]">
                  <div>
                    <label className="text-xs text-muted-foreground">
                      Current Password
                    </label>
                    <div className="relative mt-1">
                      <input
                        type={showPassword ? "text" : "password"}
                        placeholder="••••••••"
                        className="w-full px-3 py-2 pr-10 rounded-full bg-background border border-border/50 text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                      />
                      <button
                        onClick={() => setShowPassword(!showPassword)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      >
                        {showPassword ? (
                          <EyeOff className="w-4 h-4" />
                        ) : (
                          <Eye className="w-4 h-4" />
                        )}
                      </button>
                    </div>
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">
                      New Password
                    </label>
                    <input
                      type="password"
                      placeholder="••••••••"
                      className="w-full mt-1 px-3 py-2 rounded-full bg-background border border-border/50 text-foreground text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all"
                    />
                  </div>
                  <button
                    onClick={() =>
                      toast.success("Password updated successfully")
                    }
                    className="w-full mt-2 px-4 py-2.5 rounded-full bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors shadow-sm shadow-primary/15"
                  >
                    Update Password
                  </button>
                </div>
              </div>

              {/* Danger Zone */}
              <div className="space-y-4">
                <h4 className="text-sm font-medium text-destructive">
                  Danger Zone
                </h4>
                <div className="p-4 rounded-xl border border-destructive/30 bg-destructive/5">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium text-foreground">
                        Delete Account
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Permanently delete your account and all data
                      </p>
                    </div>
                    <button
                      onClick={() =>
                        toast.error(
                          "Account deletion requires confirmation via email"
                        )
                      }
                      className="px-5 py-2 rounded-full bg-destructive text-destructive-foreground text-sm font-medium hover:bg-destructive/90 transition-colors flex items-center gap-2 shadow-sm"
                    >
                      <Trash2 className="w-4 h-4" />
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Appearance Tab */}
          {activeTab === "appearance" && (
            <div className="space-y-8 animate-fade-in-up">
              <div>
                <h3 className="text-xl font-semibold text-foreground mb-2">
                  Appearance
                </h3>
                <p className="text-sm text-muted-foreground">
                  Customize how CODEXA looks and feels on your device.
                </p>
              </div>

              {/* Theme Selection */}
              <div className="space-y-3">
                <h4 className="text-sm font-medium text-foreground" id="theme-label">
                  Theme
                </h4>
                <PillOptionGroup className="w-full justify-between sm:w-auto" labelId="theme-label">
                  {(
                    [
                      { id: "light" as ThemeType, label: "Light", icon: Sun },
                      { id: "dark" as ThemeType, label: "Dark", icon: Moon },
                      {
                        id: "original" as ThemeType,
                        label: "Original",
                        icon: Sparkles,
                      },
                      { id: "gray" as ThemeType, label: "Gray", icon: Monitor },
                    ] as const
                  ).map((option) => (
                    <PillOption
                      key={option.id}
                      icon={option.icon}
                      selected={theme === option.id}
                      onClick={() => handleThemeChange(option.id)}
                      className="flex-1 sm:flex-initial min-w-0"
                    >
                      <span className="truncate">{option.label}</span>
                    </PillOption>
                  ))}
                </PillOptionGroup>
              </div>

              {/* Accent Color */}
              <div className="space-y-3">
                <h4 className="text-sm font-medium text-foreground">
                  Accent Color
                </h4>
                <PillOptionGroup className="max-w-full justify-start gap-1.5 py-2 px-2">
                  {accentColors.map((color, index) => (
                    <button
                      key={index}
                      type="button"
                      title={color.name}
                      onClick={() => handleAccentChange(index)}
                      className={cn(
                        "h-10 w-10 shrink-0 rounded-full transition-all duration-200 hover:scale-105 relative",
                        getAccentColorClass(index),
                        selectedAccent === index &&
                          "ring-2 ring-offset-2 ring-offset-background ring-primary scale-105 shadow-md",
                      )}
                    >
                      {selectedAccent === index && (
                        <span className="absolute inset-0 flex items-center justify-center">
                          <span className="h-2 w-2 rounded-full bg-white shadow-sm" />
                        </span>
                      )}
                    </button>
                  ))}
                </PillOptionGroup>
                <p className="text-xs text-muted-foreground">
                  Selected: {accentColors[selectedAccent].name}
                </p>
              </div>

              {/* Custom Accent Color Picker */}
              {selectedAccent === CUSTOM_ACCENT_INDEX && (
                <div className="space-y-4 p-4 rounded-2xl border border-primary/30 bg-primary/5">
                  <h4 className="text-sm font-medium text-foreground">
                    Custom Accent Color
                  </h4>
                  <div className="flex items-center gap-4">
                    <div className="relative">
                      <input
                        type="color"
                        value={customColor}
                        onChange={(e) => handleCustomColorChange(e.target.value)}
                        className="w-16 h-16 rounded-xl cursor-pointer border-2 border-border/50"
                      />
                    </div>
                    <div className="flex-1 space-y-2">
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          value={customColor}
                          onChange={(e) => handleCustomColorChange(e.target.value)}
                          placeholder="#3b82f6"
                          className="flex-1 px-3 py-2 text-sm bg-secondary border border-border/50 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
                        />
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Pick any color or enter a hex value for accents only.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Font Size */}
              <div className="space-y-3">
                <h4 className="text-sm font-medium text-foreground" id="font-size-label">
                  Font Size
                </h4>
                <PillOptionGroup className="w-full flex-wrap" labelId="font-size-label">
                  {[12, 14, 16, 18, 20, 22, 24].map((px) => (
                    <PillOption
                      key={px}
                      selected={fontSize === px}
                      onClick={() => handleFontSizeChange(px)}
                      className="min-w-[2.75rem] justify-center px-3"
                    >
                      {px}
                    </PillOption>
                  ))}
                </PillOptionGroup>
                <div className="rounded-full border border-border/60 bg-secondary/20 dark:bg-white/[0.04] px-4 py-3 flex items-center gap-3">
                  <span className="text-xs text-muted-foreground shrink-0 w-6">12</span>
                  <input
                    type="range"
                    min="12"
                    max="24"
                    step="1"
                    value={fontSize}
                    onChange={handleSliderChange}
                    className="flex-1 h-2 bg-muted/80 dark:bg-white/10 rounded-full appearance-none cursor-pointer accent-primary [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:shadow-lg [&::-webkit-slider-thumb]:cursor-pointer [&::-moz-range-thumb]:w-5 [&::-moz-range-thumb]:h-5 [&::-moz-range-thumb]:bg-primary [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:cursor-pointer"
                  />
                  <span className="text-xs text-muted-foreground shrink-0 w-6 text-right">24</span>
                  <span className="text-xs font-medium text-foreground tabular-nums min-w-[2.5rem] text-center border-l border-border/50 pl-3">
                    {fontSize}px
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">
                  Presets or fine-tune with the slider (12–24px).
                </p>
              </div>

              {/* Animations Toggle */}
              <SettingsPillRow>
                <div className="min-w-0 pr-2">
                  <h4 className="text-sm font-medium text-foreground">
                    Enable Animations
                  </h4>
                  <p className="text-xs text-muted-foreground mt-1">
                    Show smooth transitions and micro-interactions
                  </p>
                </div>
                <SettingsPillSwitch
                  enabled={animationsEnabled}
                  onToggle={(v) => {
                    setAnimationsEnabled(v);
                    toast.success(
                      v ? "Animations enabled" : "Animations disabled",
                    );
                  }}
                />
              </SettingsPillRow>

              {/* Compact Mode Toggle */}
              <SettingsPillRow>
                <div className="min-w-0 pr-2">
                  <h4 className="text-sm font-medium text-foreground">
                    Compact Mode
                  </h4>
                  <p className="text-xs text-muted-foreground mt-1">
                    Reduce spacing and padding for a denser layout
                  </p>
                </div>
                <SettingsPillSwitch
                  enabled={compactMode}
                  onToggle={(v) => {
                    setCompactMode(v);
                    toast.success(
                      v ? "Compact mode enabled" : "Compact mode disabled",
                    );
                  }}
                />
              </SettingsPillRow>

              {/* Reset Button */}
              <button
                onClick={handleResetSettings}
                className="flex items-center gap-2 px-5 py-2.5 rounded-full border border-border/50 text-muted-foreground hover:text-foreground hover:bg-secondary/50 transition-all"
              >
                <RotateCcw className="w-4 h-4" />
                <span className="text-sm">Reset to defaults</span>
              </button>
            </div>
          )}

          {/* AI Settings Tab */}
          {activeTab === "ai" && (
            <div className="space-y-8 animate-fade-in-up">
              <div>
                <h3 className="text-xl font-semibold text-foreground mb-2">
                  AI Settings
                </h3>
                <p className="text-sm text-muted-foreground">
                  Configure how CODEXA responds and generates content.
                </p>
              </div>

              {/* Model Selection */}
              <div className="space-y-3">
                <h4 className="text-sm font-medium text-foreground">
                  AI Model
                </h4>
                <div className="space-y-2">
                  {[
                    {
                      name: "CODEXA Pro",
                      desc: "Most capable, best for complex tasks",
                      badge: "Recommended",
                      tokens: "8K context",
                    },
                    {
                      name: "CODEXA Fast",
                      desc: "Optimized for speed",
                      badge: null,
                      tokens: "4K context",
                    },
                    {
                      name: "CODEXA Light",
                      desc: "Lightweight, cost-effective",
                      badge: null,
                      tokens: "2K context",
                    },
                  ].map((model, index) => (
                    <PillSelectRow
                      key={model.name}
                      selected={selectedModel === index}
                      onClick={() => handleModelChange(index)}
                      title={model.name}
                      description={model.desc}
                      footer={model.tokens}
                      badge={
                        model.badge ? (
                          <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary/20 text-primary font-medium">
                            {model.badge}
                          </span>
                        ) : null
                      }
                    />
                  ))}
                </div>
              </div>

              {/* Response Style */}
              <div className="space-y-3">
                <h4 className="text-sm font-medium text-foreground" id="response-style-label">
                  Response Style
                </h4>
                <PillOptionGroup
                  className="w-full justify-stretch sm:w-auto"
                  labelId="response-style-label"
                >
                  {[
                    { name: "Concise", desc: "Brief", index: 0 },
                    { name: "Balanced", desc: "Default", index: 1 },
                    { name: "Detailed", desc: "Thorough", index: 2 },
                  ].map((style) => (
                    <PillOption
                      key={style.name}
                      selected={responseStyle === style.index}
                      onClick={() => handleResponseStyleChange(style.index)}
                      className="flex-1 flex-col gap-0 py-2.5 sm:flex-initial sm:flex-row"
                    >
                      <span>{style.name}</span>
                      <span className="text-[10px] font-normal opacity-70">
                        {style.desc}
                      </span>
                    </PillOption>
                  ))}
                </PillOptionGroup>
              </div>

              {/* Additional AI Settings */}
              <div className="space-y-2.5">
                <h4 className="text-sm font-medium text-foreground">
                  Additional Options
                </h4>
                <SettingsPillRow>
                  <div className="min-w-0 pr-2">
                    <p className="text-sm font-medium text-foreground">
                      Code Formatting
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Automatically format code in responses
                    </p>
                  </div>
                  <SettingsPillSwitch
                    enabled={codeFormatting}
                    onToggle={(v) => {
                      setCodeFormatting(v);
                      toast.success(
                        v ? "Code formatting enabled" : "Code formatting disabled",
                      );
                    }}
                  />
                </SettingsPillRow>
                <SettingsPillRow>
                  <div className="min-w-0 pr-2">
                    <p className="text-sm font-medium text-foreground">
                      Streaming Responses
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Show responses as they are generated
                    </p>
                  </div>
                  <SettingsPillSwitch
                    enabled={streamingEnabled}
                    onToggle={(v) => {
                      setStreamingEnabled(v);
                      toast.success(
                        v ? "Streaming enabled" : "Streaming disabled",
                      );
                    }}
                  />
                </SettingsPillRow>
                <SettingsPillRow>
                  <div className="min-w-0 pr-2">
                    <p className="text-sm font-medium text-foreground">
                      Auto-save Conversations
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Automatically save chat history
                    </p>
                  </div>
                  <SettingsPillSwitch
                    enabled={autoSave}
                    onToggle={(v) => {
                      setAutoSave(v);
                      toast.success(
                        v ? "Auto-save enabled" : "Auto-save disabled",
                      );
                    }}
                  />
                </SettingsPillRow>
              </div>
            </div>
          )}

          {/* Notifications Tab */}
          {activeTab === "notifications" && (
            <div className="space-y-8 animate-fade-in-up">
              <div>
                <h3 className="text-xl font-semibold text-foreground mb-2">
                  Notifications
                </h3>
                <p className="text-sm text-muted-foreground">
                  Manage your notification preferences.
                </p>
              </div>

              {/* Notifications Toggle */}
              <SettingsPillRow>
                <div className="min-w-0 pr-2">
                  <h4 className="text-sm font-medium text-foreground">
                    Push Notifications
                  </h4>
                  <p className="text-xs text-muted-foreground mt-1">
                    Receive notifications for important updates
                  </p>
                </div>
                <SettingsPillSwitch
                  enabled={notificationsEnabled}
                  onToggle={(v) => {
                    setNotificationsEnabled(v);
                    toast.success(
                      v ? "Notifications enabled" : "Notifications disabled",
                    );
                  }}
                />
              </SettingsPillRow>

              {/* Sound Toggle */}
              <SettingsPillRow>
                <div className="min-w-0 pr-2">
                  <h4 className="text-sm font-medium text-foreground">
                    Sound Effects
                  </h4>
                  <p className="text-xs text-muted-foreground mt-1">
                    Play sounds for notifications and actions
                  </p>
                </div>
                <SettingsPillSwitch
                  enabled={soundEnabled}
                  onToggle={(v) => {
                    setSoundEnabled(v);
                    toast.success(
                      v ? "Sound effects enabled" : "Sound effects disabled",
                    );
                  }}
                />
              </SettingsPillRow>

              {/* Email Notifications */}
              <SettingsPillRow>
                <div className="min-w-0 pr-2">
                  <h4 className="text-sm font-medium text-foreground">
                    Email Notifications
                  </h4>
                  <p className="text-xs text-muted-foreground mt-1">
                    Receive important updates via email
                  </p>
                </div>
                <SettingsPillSwitch
                  enabled={emailNotifications}
                  onToggle={(v) => {
                    setEmailNotifications(v);
                    toast.success(
                      v ? "Email notifications enabled" : "Email notifications disabled",
                    );
                  }}
                />
              </SettingsPillRow>
            </div>
          )}

          {/* Privacy Tab */}
          {activeTab === "privacy" && (
            <div className="space-y-8 animate-fade-in-up">
              <div>
                <h3 className="text-xl font-semibold text-foreground mb-2">
                  Privacy & Security
                </h3>
                <p className="text-sm text-muted-foreground">
                  Manage your privacy settings and security options.
                </p>
              </div>

              {/* Two-Factor Authentication */}
              <SettingsPillRow>
                <div className="flex items-center gap-3 min-w-0 pr-2">
                  <div className="w-10 h-10 rounded-full bg-primary/12 flex items-center justify-center shrink-0 ring-1 ring-primary/15">
                    <Smartphone className="w-5 h-5 text-primary" />
                  </div>
                  <div className="min-w-0">
                    <h4 className="text-sm font-medium text-foreground">
                      Two-Factor Authentication
                    </h4>
                    <p className="text-xs text-muted-foreground mt-1">
                      Add an extra layer of security to your account
                    </p>
                  </div>
                </div>
                <SettingsPillSwitch
                  enabled={twoFactorEnabled}
                  onToggle={(v) => {
                    setTwoFactorEnabled(v);
                    toast.success(v ? "2FA enabled" : "2FA disabled");
                  }}
                />
              </SettingsPillRow>

              {/* Data Collection */}
              <SettingsPillRow>
                <div className="flex items-center gap-3 min-w-0 pr-2">
                  <div className="w-10 h-10 rounded-full bg-primary/12 flex items-center justify-center shrink-0 ring-1 ring-primary/15">
                    <History className="w-5 h-5 text-primary" />
                  </div>
                  <div className="min-w-0">
                    <h4 className="text-sm font-medium text-foreground">
                      Data Collection
                    </h4>
                    <p className="text-xs text-muted-foreground mt-1">
                      Allow anonymous usage data to improve the service
                    </p>
                  </div>
                </div>
                <SettingsPillSwitch
                  enabled={dataCollection}
                  onToggle={(v) => {
                    setDataCollection(v);
                    toast.success(
                      v ? "Data collection enabled" : "Data collection disabled",
                    );
                  }}
                />
              </SettingsPillRow>

              {/* Session Management */}
              <div className="space-y-4">
                <h4 className="text-sm font-medium text-foreground">
                  Active Sessions
                </h4>
                <div className="p-4 rounded-full border border-border/55 bg-secondary/20 dark:bg-white/[0.04] space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-full bg-muted/60 dark:bg-white/10 flex items-center justify-center">
                        <Monitor className="w-4 h-4 text-muted-foreground" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-foreground">
                          MacBook Pro - Chrome
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Current session
                        </p>
                      </div>
                    </div>
                    <span className="text-xs text-emerald-500">Active</span>
                  </div>
                  <button
                    onClick={() =>
                      toast.success("All other sessions have been logged out")
                    }
                    className="w-full px-4 py-2.5 rounded-full border border-destructive/35 text-destructive text-sm font-medium hover:bg-destructive/10 transition-colors"
                  >
                    Log out of all other sessions
                  </button>
                </div>
              </div>

              {/* Download Data */}
              <div className="p-4 rounded-full border border-border/55 bg-secondary/20 dark:bg-white/[0.04]">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-10 h-10 rounded-full bg-primary/12 flex items-center justify-center shrink-0 ring-1 ring-primary/15">
                      <Download className="w-5 h-5 text-primary" />
                    </div>
                    <div>
                      <h4 className="text-sm font-medium text-foreground">
                        Download Your Data
                      </h4>
                      <p className="text-xs text-muted-foreground mt-1">
                        Get a copy of all your data
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() =>
                      toast.success(
                        "Data export started. You'll receive an email when ready."
                      )
                    }
                    className="shrink-0 px-5 py-2 rounded-full bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors shadow-sm shadow-primary/20"
                  >
                    Export
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Shortcuts Tab */}
          {activeTab === "shortcuts" && (
            <div className="space-y-8 animate-fade-in-up">
              <div>
                <h3 className="text-xl font-semibold text-foreground mb-2">
                  Keyboard Shortcuts
                </h3>
                <p className="text-sm text-muted-foreground">
                  Quick keyboard shortcuts to navigate the app efficiently.
                </p>
              </div>

              <div className="space-y-2">
                {shortcuts.map((shortcut, index) => (
                  <div
                    key={index}
                    className="flex items-center justify-between gap-3 px-4 py-3 rounded-full border border-border/55 bg-secondary/20 dark:bg-white/[0.04]"
                  >
                    <span className="text-sm font-medium text-foreground">
                      {shortcut.action}
                    </span>
                    <div className="flex items-center gap-1 shrink-0">
                      {shortcut.keys.map((key, keyIndex) => (
                        <kbd
                          key={keyIndex}
                          className="px-2.5 py-1 rounded-full bg-background/90 border border-border/60 text-[11px] font-mono text-muted-foreground shadow-sm"
                        >
                          {key}
                        </kbd>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Language Tab */}
          {activeTab === "language" && (
            <div className="space-y-8 animate-fade-in-up">
              <div>
                <h3 className="text-xl font-semibold text-foreground mb-2">
                  Language
                </h3>
                <p className="text-sm text-muted-foreground">
                  Choose your preferred language for the interface.
                </p>
              </div>

              <div className="space-y-3">
                <h4
                  className="text-sm font-medium text-foreground"
                  id="language-label"
                >
                  Interface language
                </h4>
                <PillOptionGroup
                  className="w-full flex-wrap justify-start"
                  labelId="language-label"
                >
                {languages.map((lang) => (
                  <PillOption
                    key={lang.code}
                    selected={selectedLanguage === lang.code}
                    onClick={() => {
                      setSelectedLanguage(lang.code);
                      toast.success(`Language changed to ${lang.name}`);
                    }}
                    className="gap-2"
                  >
                    <span className="text-base leading-none">{lang.flag}</span>
                    <span>{lang.name}</span>
                  </PillOption>
                ))}
                </PillOptionGroup>
              </div>
            </div>
          )}
        </div>
        </div>
      </GlassCard>
    </div>
  );
}
