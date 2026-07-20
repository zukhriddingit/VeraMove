import type {
  AccessDetailsView,
  InventoryItemView,
  JobView,
  MoveDetailsView,
  ServiceDetailsView,
} from "@/lib/api";
import { longDate } from "@/lib/format";
import {
  Building2,
  Calendar,
  CheckCircle2,
  Lock,
  MapPin,
  Package,
  Pencil,
  PlusCircle,
  Shield,
  Sparkles,
  Trash2,
  AlertTriangle,
} from "lucide-react";
import { StatusPill } from "./StatusPill";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

// -------------------------------------------------------------------------
// Field-level state visuals
// -------------------------------------------------------------------------
type FieldStatus = "extracted" | "edited" | "missing" | "warning" | "confirmed";

function statusMeta(status: FieldStatus) {
  switch (status) {
    case "extracted":
      return {
        tone: "info" as const,
        label: "Extracted",
        icon: <Sparkles className="h-3 w-3" aria-hidden />,
      };
    case "edited":
      return {
        tone: "info" as const,
        label: "Edited",
        icon: <Pencil className="h-3 w-3" aria-hidden />,
      };
    case "missing":
      return {
        tone: "risk" as const,
        label: "Missing",
        icon: <AlertTriangle className="h-3 w-3" aria-hidden />,
      };
    case "warning":
      return {
        tone: "caution" as const,
        label: "Review",
        icon: <AlertTriangle className="h-3 w-3" aria-hidden />,
      };
    case "confirmed":
      return {
        tone: "verified" as const,
        label: "Confirmed",
        icon: <CheckCircle2 className="h-3 w-3" aria-hidden />,
      };
  }
}

function rowBorderClass(status: FieldStatus) {
  switch (status) {
    case "missing":
      return "border-l-risk";
    case "warning":
      return "border-l-caution";
    case "edited":
      return "border-l-primary";
    case "confirmed":
      return "border-l-verified";
    default:
      return "border-l-transparent";
  }
}

// -------------------------------------------------------------------------
// FieldRow — one editable line item.
// -------------------------------------------------------------------------
function FieldRow({
  label,
  status,
  warning,
  editor,
  children,
  locked,
  onEditStart,
  onCancel,
  onSave,
}: {
  label: string;
  status: FieldStatus;
  warning?: string;
  editor?: ReactNode; // when provided, an Edit button toggles it
  children: ReactNode;
  locked?: boolean;
  onEditStart?: () => void;
  onCancel?: () => void;
  onSave?: () => void | Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const meta = statusMeta(status);
  const canEdit = !locked && !!editor;

  return (
    <div
      className={cn(
        "flex flex-col gap-1.5 border-l-2 py-3 pl-3 pr-1",
        rowBorderClass(status),
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </div>
        <StatusPill tone={meta.tone}>
          {meta.icon}
          {meta.label}
        </StatusPill>
        {canEdit && !editing && (
          <button
            type="button"
            onClick={() => {
              onEditStart?.();
              setEditing(true);
            }}
            className="ml-auto inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs text-primary hover:bg-primary/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
            aria-label={`Edit ${label}`}
          >
            <Pencil className="h-3 w-3" />
            Edit
          </button>
        )}
      </div>

      {editing && editor ? (
        <div className="rounded-lg border border-border bg-surface-muted p-3">
          {editor}
          <div className="mt-3 flex justify-end gap-2">
            <Button
              size="sm"
              variant="ghost"
              disabled={saving}
              onClick={() => {
                onCancel?.();
                setSaveError(null);
                setEditing(false);
              }}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              disabled={saving}
              onClick={async () => {
                setSaving(true);
                setSaveError(null);
                try {
                  await onSave?.();
                  setEditing(false);
                } catch (error) {
                  setSaveError(
                    error instanceof Error
                      ? error.message
                      : "Could not save this change. Please try again.",
                  );
                } finally {
                  setSaving(false);
                }
              }}
            >
              {saving ? "Saving…" : "Save changes"}
            </Button>
          </div>
          {saveError && (
            <p role="alert" className="mt-2 text-right text-xs text-risk">
              {saveError}
            </p>
          )}
        </div>
      ) : (
        <div className="text-sm text-foreground">
          {status === "missing" ? (
            <span className="text-risk">— required, please add</span>
          ) : (
            children
          )}
        </div>
      )}

      {warning && !editing && (
        <p className="flex items-start gap-1.5 text-xs text-caution-foreground">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
          {warning}
        </p>
      )}
    </div>
  );
}

// -------------------------------------------------------------------------
// Section wrapper
// -------------------------------------------------------------------------
function Section({
  icon,
  title,
  children,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-border bg-surface p-5">
      <header className="flex items-center gap-2 border-b border-border/60 pb-3">
        <div className="text-primary">{icon}</div>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-foreground">
          {title}
        </h3>
      </header>
      <div className="divide-y divide-border/60">{children}</div>
    </section>
  );
}

// -------------------------------------------------------------------------
// JobSpecSummary — editable review of the whole spec.
// -------------------------------------------------------------------------
export interface JobSpecSummaryProps {
  job: JobView;
  locked?: boolean;
  onChange?: (patch: Partial<JobView>, fieldKey?: string) => void;
  onRestore?: (snapshot: JobView) => void;
  onCommit?: (fieldKey: string) => void | Promise<void>;
}

export function JobSpecSummary({
  job,
  locked = false,
  onChange,
  onRestore,
  onCommit,
}: JobSpecSummaryProps) {
  const [editSnapshot, setEditSnapshot] = useState<JobView | null>(null);
  const missing = new Set(job.missingFields ?? []);
  const edited = new Set(job.editedFields ?? []);
  const warnings = job.fieldWarnings ?? {};

  function fieldStatus(key: string): FieldStatus {
    if (missing.has(key)) return "missing";
    if (warnings[key]) return "warning";
    if (locked) return "confirmed";
    if (edited.has(key)) return "edited";
    return "extracted";
  }

  function lifecycle(fieldKey: string) {
    return {
      onEditStart: () => setEditSnapshot(structuredClone(job)),
      onCancel: () => {
        if (editSnapshot) onRestore?.(editSnapshot);
        setEditSnapshot(null);
      },
      onSave: async () => {
        await onCommit?.(fieldKey);
        setEditSnapshot(null);
      },
    };
  }

  function patchMove(patch: Partial<MoveDetailsView>, fieldKey: string) {
    onChange?.({ move: { ...job.move, ...patch } }, fieldKey);
  }
  function patchAccess(patch: Partial<AccessDetailsView>, fieldKey: string) {
    onChange?.({ access: { ...job.access, ...patch } }, fieldKey);
  }
  function patchServices(patch: Partial<ServiceDetailsView>, fieldKey: string) {
    onChange?.({ services: { ...job.services, ...patch } }, fieldKey);
  }
  function patchInventory(next: InventoryItemView[]) {
    onChange?.({ inventory: next }, "inventory");
  }

  const src = job.extractionSource;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">Move specification</h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            One spec, reused on every vendor call — that's what keeps the
            quotes comparable.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {job.synthetic && <StatusPill tone="caution">Synthetic demo data</StatusPill>}
          {src && (
            <StatusPill tone="info">
              <Sparkles className="h-3 w-3" aria-hidden />
              From {src === "voice" ? "voice interview" : src === "document" ? "uploaded document" : "manual entry"}
            </StatusPill>
          )}
          {locked && (
            <StatusPill tone="verified">
              <Lock className="h-3 w-3" aria-hidden />
              Locked for calls
            </StatusPill>
          )}
        </div>
      </div>

      {/* Move overview */}
      <Section icon={<MapPin className="h-4 w-4" />} title="Move overview">
        <FieldRow
          label="Route"
          status={fieldStatus("move.route")}
          locked={locked}
          {...lifecycle("move.route")}
          editor={
            <div className="grid gap-2 sm:grid-cols-2">
              <div>
                <Label htmlFor="oc">Origin city</Label>
                <Input
                  id="oc"
                  value={job.move.originCity}
                  onChange={(e) => patchMove({ originCity: e.target.value }, "move.route")}
                />
              </div>
              <div>
                <Label htmlFor="os">Origin state</Label>
                <Input
                  id="os"
                  value={job.move.originState}
                  onChange={(e) => patchMove({ originState: e.target.value }, "move.route")}
                />
              </div>
              <div>
                <Label htmlFor="dc">Destination city</Label>
                <Input
                  id="dc"
                  value={job.move.destinationCity}
                  onChange={(e) => patchMove({ destinationCity: e.target.value }, "move.route")}
                />
              </div>
              <div>
                <Label htmlFor="ds">Destination state</Label>
                <Input
                  id="ds"
                  value={job.move.destinationState}
                  onChange={(e) => patchMove({ destinationState: e.target.value }, "move.route")}
                />
              </div>
            </div>
          }
        >
          {job.move.originCity}, {job.move.originState} → {job.move.destinationCity}, {job.move.destinationState}
        </FieldRow>

        <FieldRow
          label="Move date"
          status={fieldStatus("move.date")}
          warning={warnings["move.date"]}
          locked={locked}
          {...lifecycle("move.date")}
          editor={
            <div>
              <Label htmlFor="md">Move date</Label>
              <Input
                id="md"
                type="date"
                value={job.move.date}
                onChange={(e) => patchMove({ date: e.target.value }, "move.date")}
              />
            </div>
          }
        >
          <span className="flex items-center gap-1.5">
            <Calendar className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
            {longDate(job.move.date)}
          </span>
        </FieldRow>

        <FieldRow
          label="Date flexibility"
          status={fieldStatus("move.flexibilityDays")}
          locked={locked}
          {...lifecycle("move.flexibilityDays")}
          editor={
            <div>
              <Label htmlFor="mf">Flexible by (days)</Label>
              <Input
                id="mf"
                type="number"
                min={0}
                value={job.move.flexibilityDays}
                onChange={(e) =>
                  patchMove({ flexibilityDays: Number(e.target.value) }, "move.flexibilityDays")}
              />
            </div>
          }
        >
          {missing.has("move.flexibilityDays")
            ? null
            : `± ${job.move.flexibilityDays} day${job.move.flexibilityDays === 1 ? "" : "s"}`}
        </FieldRow>

        <FieldRow
          label="Home type"
          status={fieldStatus("homeType")}
          locked={locked}
          {...lifecycle("homeType")}
          editor={
            <div className="grid gap-2 sm:grid-cols-2">
              <div>
                <Label htmlFor="ht">Dwelling type</Label>
                <Select
                  value={job.homeType}
                  onValueChange={(v) => onChange?.({ homeType: v }, "homeType")}
                >
                  <SelectTrigger id="ht"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {[
                      ["apartment", "Apartment"],
                      ["condo", "Condo"],
                      ["house", "House"],
                      ["townhouse", "Townhouse"],
                      ["storage_unit", "Storage unit"],
                      ["other", "Other"],
                    ].map(([value, label]) => (
                      <SelectItem key={value} value={value}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="br">Bedrooms</Label>
                <Input
                  id="br"
                  type="number"
                  min={0}
                  value={job.bedrooms ?? 0}
                  onChange={(e) =>
                    onChange?.({ bedrooms: Number(e.target.value) }, "homeType")}
                />
              </div>
            </div>
          }
        >
          {job.bedrooms ?? "?"}-bedroom {job.homeType.toLowerCase()}
        </FieldRow>
      </Section>

      {/* Origin access */}
      <Section icon={<Building2 className="h-4 w-4" />} title="Origin access">
        <FieldRow
          label="Floor & elevator"
          status={fieldStatus("access.origin")}
          locked={locked}
          {...lifecycle("access.origin")}
          editor={
            <div className="grid gap-2 sm:grid-cols-2">
              <div>
                <Label htmlFor="of">Origin floor</Label>
                <Input
                  id="of"
                  type="number"
                  min={0}
                  value={job.access.originFloor}
                  onChange={(e) =>
                    patchAccess({ originFloor: Number(e.target.value) }, "access.origin")}
                />
              </div>
              <div className="flex items-end gap-2">
                <Checkbox
                  id="oe"
                  checked={job.access.originElevator}
                  onCheckedChange={(v) =>
                    patchAccess({ originElevator: !!v }, "access.origin")}
                />
                <Label htmlFor="oe">Elevator available</Label>
              </div>
            </div>
          }
        >
          Floor {job.access.originFloor} ·{" "}
          {job.access.originElevator ? "Elevator" : "Stairs only"}
          {!job.access.originElevator && job.access.originFloor > 1 && (
            <span className="text-muted-foreground"> · stair carry required</span>
          )}
        </FieldRow>

        <FieldRow
          label="Parking / long carry"
          status={fieldStatus("access.longCarryFt")}
          locked={locked}
          {...lifecycle("access.longCarryFt")}
          editor={
            <div>
              <Label htmlFor="lc">Long-carry distance (ft)</Label>
              <Input
                id="lc"
                type="number"
                min={0}
                value={job.access.longCarryFt}
                onChange={(e) =>
                  patchAccess({ longCarryFt: Number(e.target.value) }, "access.longCarryFt")}
              />
            </div>
          }
        >
          {missing.has("access.longCarryFt")
            ? null
            : job.access.longCarryFt > 0
              ? `~${job.access.longCarryFt} ft from parking to door`
              : "None (truck at door)"}
        </FieldRow>
      </Section>

      {/* Destination access */}
      <Section icon={<Building2 className="h-4 w-4" />} title="Destination access">
        <FieldRow
          label="Floor & elevator"
          status={fieldStatus("access.destination")}
          locked={locked}
          {...lifecycle("access.destination")}
          editor={
            <div className="grid gap-2 sm:grid-cols-2">
              <div>
                <Label htmlFor="df">Destination floor</Label>
                <Input
                  id="df"
                  type="number"
                  min={0}
                  value={job.access.destinationFloor}
                  onChange={(e) =>
                    patchAccess({ destinationFloor: Number(e.target.value) }, "access.destination")}
                />
              </div>
              <div className="flex items-end gap-2">
                <Checkbox
                  id="de"
                  checked={job.access.destinationElevator}
                  onCheckedChange={(v) =>
                    patchAccess({ destinationElevator: !!v }, "access.destination")}
                />
                <Label htmlFor="de">Elevator available</Label>
              </div>
            </div>
          }
        >
          Floor {job.access.destinationFloor} ·{" "}
          {job.access.destinationElevator ? "Elevator" : "Stairs only"}
        </FieldRow>
      </Section>

      {/* Inventory */}
      <Section icon={<Package className="h-4 w-4" />} title="Inventory">
        <FieldRow
          label="Items"
          status={fieldStatus("inventory")}
          warning={warnings["inventory"]}
          locked={locked}
          {...lifecycle("inventory")}
          editor={
            <InventoryEditor
              items={job.inventory}
              onChange={patchInventory}
            />
          }
        >
          <ul className="space-y-0.5">
            {job.inventory.map((i, idx) => (
              <li key={`${i.item}-${idx}`}>
                {i.qty}× {i.item}
                {i.notes ? <span className="text-muted-foreground"> — {i.notes}</span> : null}
              </li>
            ))}
            {job.inventory.length === 0 && (
              <li className="text-muted-foreground">No items listed.</li>
            )}
          </ul>
        </FieldRow>

        <FieldRow
          label="Oversized or fragile"
          status={fieldStatus("extras.oversizedOrFragile")}
          locked={locked}
          {...lifecycle("extras.oversizedOrFragile")}
          editor={
            <div>
              <Label htmlFor="ov">Oversized or fragile items (comma separated)</Label>
              <Input
                id="ov"
                value={(job.extras?.oversizedOrFragile ?? []).join(", ")}
                onChange={(e) =>
                  onChange?.({
                    extras: {
                      disassembly: job.extras?.disassembly ?? false,
                      storage: job.extras?.storage ?? false,
                      oversizedOrFragile: e.target.value
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    },
                  }, "extras.oversizedOrFragile")
                }
              />
            </div>
          }
        >
          {(job.extras?.oversizedOrFragile ?? []).length === 0
            ? "None declared"
            : job.extras!.oversizedOrFragile.join(", ")}
        </FieldRow>
      </Section>

      {/* Extra services */}
      <Section icon={<Sparkles className="h-4 w-4" />} title="Extra services">
        <FieldRow
          label="Packing service"
          status={fieldStatus("services.packing")}
          locked={locked}
          {...lifecycle("services.packing")}
          editor={
            <div className="flex items-center gap-2">
              <Checkbox
                id="pk"
                checked={job.services.packing}
                onCheckedChange={(v) =>
                  patchServices({ packing: !!v }, "services.packing")}
              />
              <Label htmlFor="pk">Include packing service</Label>
            </div>
          }
        >
          {job.services.packing ? "Included" : "Not included"}
        </FieldRow>

        <FieldRow
          label="Disassembly"
          status={fieldStatus("extras.disassembly")}
          locked={locked}
          {...lifecycle("extras.disassembly")}
          editor={
            <div className="flex items-center gap-2">
              <Checkbox
                id="da"
                checked={!!job.extras?.disassembly}
                onCheckedChange={(v) =>
                  onChange?.({
                    extras: {
                      disassembly: !!v,
                      storage: job.extras?.storage ?? false,
                      oversizedOrFragile: job.extras?.oversizedOrFragile ?? [],
                    },
                  }, "extras.disassembly")
                }
              />
              <Label htmlFor="da">Items require disassembly</Label>
            </div>
          }
        >
          {job.extras?.disassembly ? "Required (e.g. bed frame)" : "Not required"}
        </FieldRow>

        <FieldRow
          label="Storage"
          status={fieldStatus("extras.storage")}
          locked={locked}
          {...lifecycle("extras.storage")}
          editor={
            <div className="flex items-center gap-2">
              <Checkbox
                id="st"
                checked={!!job.extras?.storage}
                onCheckedChange={(v) =>
                  onChange?.({
                    extras: {
                      disassembly: job.extras?.disassembly ?? false,
                      storage: !!v,
                      oversizedOrFragile: job.extras?.oversizedOrFragile ?? [],
                    },
                  }, "extras.storage")
                }
              />
              <Label htmlFor="st">Overnight storage needed</Label>
            </div>
          }
        >
          {job.extras?.storage ? "Requested" : "Not needed"}
        </FieldRow>
      </Section>

      {/* Insurance & constraints */}
      <Section icon={<Shield className="h-4 w-4" />} title="Insurance & constraints">
        <FieldRow
          label="Insurance tier"
          status={fieldStatus("services.insuranceTier")}
          locked={locked}
          {...lifecycle("services.insuranceTier")}
          editor={
            <div>
              <Label htmlFor="ins">Coverage</Label>
              <Select
                value={job.services.insuranceTier}
                onValueChange={(v) =>
                  patchServices(
                    { insuranceTier: v as ServiceDetailsView["insuranceTier"] },
                    "services.insuranceTier",
                  )
                }
              >
                <SelectTrigger id="ins"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="standard">Standard (released value)</SelectItem>
                  <SelectItem value="full-value">Full-value protection</SelectItem>
                </SelectContent>
              </Select>
            </div>
          }
        >
          {job.services.insuranceTier === "standard"
            ? "Standard released-value coverage"
            : "Full-value protection"}
        </FieldRow>

        <FieldRow
          label="Notes & constraints"
          status={fieldStatus("notes")}
          locked={locked}
          {...lifecycle("notes")}
          editor={
            <div>
              <Label htmlFor="nt">Anything else vendors should know</Label>
              <Textarea
                id="nt"
                rows={3}
                value={job.notes ?? ""}
                onChange={(e) => onChange?.({ notes: e.target.value }, "notes")}
              />
            </div>
          }
        >
          {job.notes?.trim() ? job.notes : <span className="text-muted-foreground">None</span>}
        </FieldRow>
      </Section>
    </div>
  );
}

// -------------------------------------------------------------------------
// InventoryEditor — small nested editor.
// -------------------------------------------------------------------------
function InventoryEditor({
  items,
  onChange,
}: {
  items: InventoryItemView[];
  onChange: (next: InventoryItemView[]) => void;
}) {
  function update(idx: number, patch: Partial<InventoryItemView>) {
    onChange(items.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  }
  function remove(idx: number) {
    onChange(items.filter((_, i) => i !== idx));
  }
  function add() {
    onChange([...items, { item: "", qty: 1 }]);
  }
  return (
    <div className="space-y-2">
      {items.map((it, idx) => (
        <div key={idx} className="grid grid-cols-[1fr_80px_1fr_auto] items-end gap-2">
          <div>
            <Label htmlFor={`it-${idx}`} className="sr-only">Item</Label>
            <Input
              id={`it-${idx}`}
              placeholder="Item"
              value={it.item}
              onChange={(e) => update(idx, { item: e.target.value })}
            />
          </div>
          <div>
            <Label htmlFor={`q-${idx}`} className="sr-only">Qty</Label>
            <Input
              id={`q-${idx}`}
              type="number"
              min={1}
              value={it.qty}
              onChange={(e) => update(idx, { qty: Number(e.target.value) })}
            />
          </div>
          <div>
            <Label htmlFor={`n-${idx}`} className="sr-only">Notes</Label>
            <Input
              id={`n-${idx}`}
              placeholder="Notes (optional)"
              value={it.notes ?? ""}
              onChange={(e) => update(idx, { notes: e.target.value })}
            />
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => remove(idx)}
            aria-label={`Remove ${it.item || "item"}`}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" onClick={add} className="gap-1.5">
        <PlusCircle className="h-4 w-4" /> Add item
      </Button>
    </div>
  );
}
