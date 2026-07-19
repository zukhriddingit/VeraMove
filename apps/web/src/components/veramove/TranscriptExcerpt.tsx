import { Quote } from "lucide-react";

export function TranscriptExcerpt({
  ts,
  excerpt,
  vendorName,
  className,
}: {
  ts?: string;
  excerpt?: string;
  vendorName?: string;
  className?: string;
}) {
  if (!excerpt) {
    return (
      <p className={"text-xs italic text-muted-foreground " + (className ?? "")}>
        Evidence unavailable.
      </p>
    );
  }
  return (
    <figure className={"rounded-md border border-border bg-surface-muted p-3 " + (className ?? "")}>
      <blockquote className="flex gap-2 text-sm text-foreground/90">
        <Quote className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
        <span>{excerpt}</span>
      </blockquote>
      {(ts || vendorName) && (
        <figcaption className="mt-1.5 text-xs text-muted-foreground">
          {vendorName ? <span className="font-medium">{vendorName}</span> : null}
          {vendorName && ts ? " · " : null}
          {ts ? <span className="tabular-nums">{ts}</span> : null}
        </figcaption>
      )}
    </figure>
  );
}
