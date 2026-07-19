import { Link } from "@tanstack/react-router";
import { API_BASE_URL } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";

export type StepKey = "intake" | "confirm" | "calls" | "report";

const STEPS: { key: StepKey; label: string; num: number }[] = [
  { key: "intake", label: "Intake", num: 1 },
  { key: "confirm", label: "Confirm", num: 2 },
  { key: "calls", label: "Calls", num: 3 },
  { key: "report", label: "Report", num: 4 },
];

export function Stepper({ current, jobId }: { current: StepKey; jobId?: string }) {
  const currentIdx = STEPS.findIndex((s) => s.key === current);
  return (
    <nav
      aria-label="Progress"
      className="rounded-xl border border-border bg-card/60 p-2"
    >
      <ol className="flex flex-wrap items-center gap-1 sm:gap-2">
        {STEPS.map((s, i) => {
          const isCurrent = i === currentIdx;
          const isDone = i < currentIdx;
          const clickable =
            s.key === "intake" ||
            (jobId && (s.key === "confirm" || s.key === "calls" || s.key === "report"));

          const inner = (
            <span
              className={[
                "flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm transition",
                isCurrent
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : isDone
                    ? "bg-mint/50 text-mint-foreground"
                    : "text-muted-foreground",
                clickable && !isCurrent ? "hover:bg-accent" : "",
              ].join(" ")}
            >
              <span
                className={[
                  "flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-semibold",
                  isCurrent
                    ? "bg-primary-foreground/20"
                    : isDone
                      ? "bg-primary/20 text-primary"
                      : "bg-muted",
                ].join(" ")}
              >
                {s.num}
              </span>
              <span className="font-medium">{s.label}</span>
            </span>
          );

          return (
            <li key={s.key} className="flex items-center gap-1 sm:gap-2">
              {clickable && !isCurrent ? (
                s.key === "intake" ? (
                  <Link to="/intake">{inner}</Link>
                ) : s.key === "confirm" && jobId ? (
                  <Link to="/confirm/$jobId" params={{ jobId }}>{inner}</Link>
                ) : s.key === "calls" && jobId ? (
                  <Link to="/calls/$jobId" params={{ jobId }}>{inner}</Link>
                ) : s.key === "report" && jobId ? (
                  <Link to="/report/$jobId" params={{ jobId }}>{inner}</Link>
                ) : (
                  inner
                )
              ) : (
                inner
              )}
              {i < STEPS.length - 1 && (
                <span aria-hidden className="text-muted-foreground/50">·</span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export function ErrorBox({ message }: { message: string }) {
  const looksLikeNetwork =
    /failed to fetch|networkerror|load failed|fetch failed|ECONNREFUSED/i.test(message);
  return (
    <div
      role="alert"
      className="space-y-2 rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive"
    >
      <div className="font-medium">Something went wrong</div>
      <div className="font-mono text-xs opacity-90 break-words">{message}</div>
      {looksLikeNetwork && (
        <div className="text-xs text-destructive/80">
          Can't reach the VeraMove backend. Make sure it's running and reachable at{" "}
          <code className="rounded bg-destructive/10 px-1 py-0.5">{API_BASE_URL}</code>, or
          update <code className="rounded bg-destructive/10 px-1 py-0.5">VITE_API_BASE_URL</code>.
        </div>
      )}
    </div>
  );
}

export function LoadingCard({ label = "Loading…" }: { label?: string }) {
  return (
    <div
      role="status"
      aria-label={label}
      className="space-y-4 rounded-xl border border-border bg-card p-6"
    >
      <Skeleton className="h-6 w-1/3" />
      <Skeleton className="h-4 w-2/3" />
      <div className="grid gap-3 sm:grid-cols-2">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
      <Skeleton className="h-32 w-full" />
      <span className="sr-only">{label}</span>
    </div>
  );
}
