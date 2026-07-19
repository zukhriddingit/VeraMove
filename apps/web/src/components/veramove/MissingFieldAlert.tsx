import { AlertCircle } from "lucide-react";

export function MissingFieldAlert({ fields }: { fields: string[] }) {
  if (fields.length === 0) return null;
  return (
    <div className="flex items-start gap-3 rounded-xl border border-caution/40 bg-caution-soft p-4">
      <AlertCircle className="mt-0.5 h-4 w-4 text-caution-foreground" />
      <div>
        <div className="text-sm font-medium text-caution-foreground">
          Missing information
        </div>
        <p className="mt-0.5 text-sm text-caution-foreground/80">
          {fields.join(", ")} — confirm or edit before starting calls.
        </p>
      </div>
    </div>
  );
}
