// Inline field selectors for a work item: save on change via PATCH.
import { useState } from "react";
import { Lock, Unlock } from "lucide-react";
import type { Project, WorkItemDetail, WorkItemInput, Priority } from "@/api/types";
import { useUsers } from "@/api/queries";
import { Field, Input, Select, Toggle, cn } from "@/components/ui";
import { useSprints } from "./hooks";
import { PRIORITIES } from "./common";
import { LabelPicker, ParentPicker } from "./pickers";

export function ItemFields({ item, project, onPatch, compact }: { item: WorkItemDetail; project: Project | undefined; onPatch: (p: Partial<WorkItemInput>) => void; compact?: boolean }) {
  const { data: users } = useUsers();
  const { data: sprints } = useSprints(project?.id);
  const scale = project?.settings.points_scale ?? [1, 2, 3, 5, 8, 13];
  const [reason, setReason] = useState(item.blocked_reason ?? "");
  const openSprints = (sprints ?? []).filter((s) => s.state !== "closed" || s.id === item.sprint_id);
  const sel = "h-8 text-xs";
  return (
    <div className="space-y-3">
      <div className={cn("grid gap-2.5", compact ? "grid-cols-2" : "grid-cols-2 md:grid-cols-4")}>
        <Field label="Status"><Select className={sel} value={item.status} onChange={(e) => onPatch({ status: e.target.value })} aria-label="Status">{(project?.workflow ?? []).map((s) => <option key={s.key} value={s.key}>{s.name}</option>)}</Select></Field>
        <Field label="Priority"><Select className={sel} value={item.priority} onChange={(e) => onPatch({ priority: e.target.value as Priority })} aria-label="Priority">{PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}</Select></Field>
        <Field label={project?.settings.estimation === "hours" ? "Estimate (h)" : "Points"}>
          {project?.settings.estimation === "hours"
            ? <Input type="number" min={0} className={sel} defaultValue={item.estimate_hours ?? ""} onBlur={(e) => { const v = e.target.value === "" ? null : Number(e.target.value); if (v !== item.estimate_hours) onPatch({ estimate_hours: v }); }} aria-label="Estimate hours" />
            : <Select className={cn(sel, "num")} value={item.points ?? ""} onChange={(e) => onPatch({ points: e.target.value === "" ? null : Number(e.target.value) })} aria-label="Points">
                <option value="">–</option>{[...new Set([...scale, ...(item.points != null ? [item.points] : [])])].sort((a, b) => a - b).map((p) => <option key={p} value={p}>{p}</option>)}
              </Select>}
        </Field>
        <Field label="Assignee"><Select className={sel} value={item.assignee_id ?? ""} onChange={(e) => onPatch({ assignee_id: e.target.value || null })} aria-label="Assignee"><option value="">Unassigned</option>{(users ?? []).filter((u) => u.is_active || u.id === item.assignee_id).map((u) => <option key={u.id} value={u.id}>{u.emoji} {u.name}</option>)}</Select></Field>
        <Field label="Sprint"><Select className={sel} value={item.sprint_id ?? ""} onChange={(e) => onPatch({ sprint_id: e.target.value || null })} aria-label="Sprint"><option value="">Backlog (unscheduled)</option>{openSprints.map((s) => <option key={s.id} value={s.id}>{s.name}{s.state === "active" ? " · active" : ""}</option>)}</Select></Field>
        <Field label="Due"><Input type="date" className={cn(sel, "num")} value={item.due_date ?? ""} onChange={(e) => onPatch({ due_date: e.target.value || null })} aria-label="Due date" /></Field>
        <Field label="Parent" className="col-span-2"><ParentPicker project={project} value={item.parent_id} excludeIds={[item.id, ...item.children.map((c) => c.id)]} onChange={(id) => onPatch({ parent_id: id })} /></Field>
      </div>
      <Field label="Labels"><LabelPicker projectId={project?.id} value={item.labels.map((l) => l.name)} onChange={(names) => onPatch({ labels: names })} /></Field>
      <div className={cn("flex items-center gap-3 flex-wrap rounded-[8px] px-3 py-2 border", item.blocked ? "border-rust/60 bg-rust/10" : "border-border")}>
        <Toggle checked={item.blocked} onChange={(b) => onPatch({ blocked: b, blocked_reason: b ? reason || null : null })} label={<span className="inline-flex items-center gap-1.5 font-display font-semibold text-xs uppercase tracking-wide">{item.blocked ? <Lock size={13} className="text-rust-light" /> : <Unlock size={13} className="text-text-3" />}{item.blocked ? "Blocked" : "Not blocked"}</span>} />
        {item.blocked && <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="What's in the way?" className="h-8 text-xs flex-1 min-w-[200px]" aria-label="Blocked reason"
          onBlur={() => { if (reason !== (item.blocked_reason ?? "")) onPatch({ blocked_reason: reason || null }); }} onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />}
      </div>
    </div>
  );
}
