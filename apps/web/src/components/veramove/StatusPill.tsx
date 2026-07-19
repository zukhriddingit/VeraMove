import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

type Tone = "verified" | "caution" | "risk" | "neutral" | "info";

const toneClasses: Record<Tone, string> = {
  verified: "border-verified/30 bg-verified-soft text-foreground",
  caution: "border-caution/40 bg-caution-soft text-caution-foreground",
  risk: "border-risk/30 bg-risk-soft text-foreground",
  neutral: "border-border bg-muted text-muted-foreground",
  info: "border-border bg-surface text-foreground",
};

export function StatusPill({
  tone = "neutral",
  icon,
  children,
  className,
}: {
  tone?: Tone;
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
        toneClasses[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}
