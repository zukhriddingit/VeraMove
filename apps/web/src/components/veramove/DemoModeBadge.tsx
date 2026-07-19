import { FlaskConical } from "lucide-react";

export function DemoModeBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-caution/40 bg-caution-soft px-2.5 py-1 text-xs font-medium text-caution-foreground">
      <FlaskConical className="h-3.5 w-3.5" />
      Demo mode · synthetic data
    </span>
  );
}
