import * as React from "react";
import { cn } from "@/lib/utils";
import { Switch } from "@/components/ui/switch";

/** iOS-style pill switch for settings rows */
export function SettingsPillSwitch({
  enabled,
  onToggle,
  id,
  disabled,
}: {
  enabled: boolean;
  onToggle: (next: boolean) => void;
  id?: string;
  disabled?: boolean;
}) {
  return (
    <Switch
      id={id}
      checked={enabled}
      disabled={disabled}
      onCheckedChange={onToggle}
      className={cn(
        "shrink-0",
        "data-[state=checked]:bg-primary",
        "data-[state=unchecked]:bg-input dark:data-[state=unchecked]:bg-white/12",
      )}
    />
  );
}

/** Full-width selectable row with pill (stadium) shape */
export function PillSelectRow({
  selected,
  onClick,
  title,
  description,
  footer,
  badge,
}: {
  selected: boolean;
  onClick: () => void;
  title: React.ReactNode;
  description?: React.ReactNode;
  footer?: React.ReactNode;
  badge?: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full flex items-center justify-between gap-3 rounded-full border px-4 py-3 text-left transition-all duration-200",
        selected
          ? "border-primary/45 bg-primary/12 ring-1 ring-primary/20 shadow-sm shadow-primary/10"
          : "border-border/55 bg-secondary/20 hover:border-border hover:bg-secondary/35 dark:bg-white/[0.04]",
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-foreground">{title}</span>
          {badge}
        </div>
        {description ? (
          <p className="text-xs text-muted-foreground mt-0.5">{description}</p>
        ) : null}
        {footer ? (
          <p className="text-xs text-muted-foreground/75 mt-0.5">{footer}</p>
        ) : null}
      </div>
      <div
        className={cn(
          "h-5 w-5 shrink-0 rounded-full border-2 flex items-center justify-center transition-colors",
          selected ? "border-primary bg-primary" : "border-muted-foreground/35",
        )}
        aria-hidden
      >
        {selected ? (
          <span className="h-2 w-2 rounded-full bg-primary-foreground" />
        ) : null}
      </div>
    </button>
  );
}

/** Container for horizontal pill options (segmented control) */
export function PillOptionGroup({
  children,
  className,
  labelId,
}: {
  children: React.ReactNode;
  className?: string;
  labelId?: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-labelledby={labelId}
      className={cn(
        "inline-flex flex-wrap items-center gap-0.5 p-1 rounded-full",
        "border border-border/70 bg-muted/35 dark:bg-white/[0.06]",
        "shadow-sm shadow-black/5 dark:shadow-black/20",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function PillOption({
  selected,
  onClick,
  children,
  className,
  icon: Icon,
}: {
  selected: boolean;
  onClick: () => void;
  children: React.ReactNode;
  className?: string;
  icon?: React.ComponentType<{ className?: string }>;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onClick}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-full px-3.5 py-2 text-sm font-medium transition-all duration-200",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        selected
          ? "bg-primary text-primary-foreground shadow-md shadow-primary/25"
          : "text-muted-foreground hover:text-foreground hover:bg-background/60 dark:hover:bg-white/[0.07]",
        className,
      )}
    >
      {Icon ? <Icon className="h-4 w-4 shrink-0 opacity-90" /> : null}
      {children}
    </button>
  );
}

/** Full-width setting row with pill-shaped background */
export function SettingsPillRow({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-4 px-4 py-3.5 rounded-full",
        "border border-border/60 bg-secondary/25 dark:bg-white/[0.04]",
        "shadow-sm shadow-black/[0.03] dark:shadow-none",
        className,
      )}
    >
      {children}
    </div>
  );
}
