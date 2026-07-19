import type { ReactNode } from "react";
import type { VerificationState } from "@/lib/api/types";
import { StatusPill } from "./StatusPill";
import {
  ShieldCheck,
  ShieldAlert,
  ShieldQuestion,
  Sparkles,
  XCircle,
} from "lucide-react";

const MAP: Record<
  VerificationState,
  { tone: "verified" | "caution" | "risk" | "neutral" | "info"; icon: ReactNode; label: string }
> = {
  verified: {
    tone: "verified",
    icon: <ShieldCheck className="h-3.5 w-3.5" />,
    label: "Verified",
  },
  partially_verified: {
    tone: "caution",
    icon: <ShieldAlert className="h-3.5 w-3.5" />,
    label: "Partially verified",
  },
  provisional: {
    tone: "neutral",
    icon: <ShieldQuestion className="h-3.5 w-3.5" />,
    label: "Provisional",
  },
  rejected: {
    tone: "risk",
    icon: <XCircle className="h-3.5 w-3.5" />,
    label: "Rejected",
  },
  role_play: {
    tone: "info",
    icon: <Sparkles className="h-3.5 w-3.5" />,
    label: "Role-play",
  },
  failed: {
    tone: "risk",
    icon: <XCircle className="h-3.5 w-3.5" />,
    label: "Failed",
  },
};

export function EvidenceBadge({
  state,
  className,
  synthetic,
}: {
  state?: VerificationState;
  className?: string;
  synthetic?: boolean;
}) {
  // Synthetic vendors always render as role-play regardless of underlying
  // verification state so demo data is unmistakable.
  const key: VerificationState = synthetic ? "role_play" : state ?? "provisional";
  const cfg = MAP[key];
  return (
    <StatusPill
      tone={cfg.tone}
      icon={cfg.icon}
      className={
        (key === "role_play"
          ? "border-purple-400/40 bg-purple-50 text-purple-900 dark:bg-purple-950/40 dark:text-purple-200 "
          : "") + (className ?? "")
      }
    >
      <span aria-label={`Verification: ${cfg.label}`}>{cfg.label}</span>
    </StatusPill>
  );
}
