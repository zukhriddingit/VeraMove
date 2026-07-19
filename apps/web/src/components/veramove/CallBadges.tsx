import type { CallViewOutcome, CallViewStatus } from "@/lib/api";
import {
  CheckCircle2,
  Clock,
  PhoneCall,
  PhoneOff,
  MessageSquare,
  XCircle,
  Scale,
  FileText,
} from "lucide-react";
import { StatusPill } from "./StatusPill";

const STATUS: Record<
  CallViewStatus,
  { tone: "neutral" | "info" | "verified" | "caution" | "risk"; label: string; icon: React.ReactNode }
> = {
  pending: { tone: "neutral", label: "Pending", icon: <Clock className="h-3.5 w-3.5" /> },
  queued: { tone: "neutral", label: "Queued", icon: <Clock className="h-3.5 w-3.5" /> },
  dialing: { tone: "info", label: "Dialing", icon: <PhoneCall className="h-3.5 w-3.5" /> },
  in_progress: { tone: "info", label: "In progress", icon: <PhoneCall className="h-3.5 w-3.5" /> },
  negotiating: { tone: "caution", label: "Negotiating", icon: <Scale className="h-3.5 w-3.5" /> },
  completed: { tone: "verified", label: "Completed", icon: <CheckCircle2 className="h-3.5 w-3.5" /> },
  failed: { tone: "risk", label: "Failed", icon: <PhoneOff className="h-3.5 w-3.5" /> },
};

const OUTCOME: Record<
  CallViewOutcome,
  { tone: "verified" | "caution" | "risk" | "neutral"; label: string; icon: React.ReactNode }
> = {
  itemized_quote: { tone: "verified", label: "Itemized quote", icon: <FileText className="h-3.5 w-3.5" /> },
  callback_commitment: { tone: "caution", label: "Callback committed", icon: <MessageSquare className="h-3.5 w-3.5" /> },
  documented_decline: { tone: "neutral", label: "Documented decline", icon: <XCircle className="h-3.5 w-3.5" /> },
  failed: { tone: "risk", label: "Failed call", icon: <PhoneOff className="h-3.5 w-3.5" /> },
};

export function CallStatusBadge({ status }: { status: CallViewStatus }) {
  const s = STATUS[status];
  return (
    <StatusPill tone={s.tone} icon={s.icon}>
      {s.label}
    </StatusPill>
  );
}

export function CallOutcomeBadge({ outcome }: { outcome?: CallViewOutcome }) {
  if (!outcome) return null;
  const o = OUTCOME[outcome];
  return (
    <StatusPill tone={o.tone} icon={o.icon}>
      {o.label}
    </StatusPill>
  );
}
