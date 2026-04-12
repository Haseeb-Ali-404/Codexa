import { cn } from "@/lib/utils";
import { forwardRef, HTMLAttributes } from "react";

interface GlassCardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "subtle" | "strong";
  glow?: boolean;
  hover?: boolean;
}

const GlassCard = forwardRef<HTMLDivElement, GlassCardProps>(
  ({ className, variant = "default", glow = false, hover = false, children, ...props }, ref) => {
    const variants = {
      default: "glass",
      subtle: "glass-subtle",
      strong: "glass-strong",
    };

    return (
      <div
        ref={ref}
        className={cn(
          variants[variant],
          "rounded-2xl",
          glow && "glow-subtle",
          hover && "hover-lift cursor-pointer",
          className
        )}
        {...props}
      >
        {children}
      </div>
    );
  }
);

GlassCard.displayName = "GlassCard";

export { GlassCard };
