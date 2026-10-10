// Floating bulk-action bar for selected backlog items.
import { Archive, X } from "lucide-react";
import type { Priority, Project, Sprint, User } from "@/api/types";
import { Button, Select, cn, toast } from "@/components/ui";
import { useBulkUpdate, useDeleteItem } from "@/features/items/hooks";
import { PRIORITIES } from "@/features/items/common";

export function BulkBar({ ids, project, users, sprints, onClear }: { ids: string[]; project: Project | undefined; users: User[] | undefined; sprints: Sprint[] | undefined; onClear: () => void }) {
  const bulk = useBulkUpdate();
  const del = useDeleteItem();
  if (!ids.length) return null;
  const scale = project?.settings.points_scale ?? [1, 2, 3, 5, 8, 13];
  const apply = (patch: Parameters<typeof bulk.mutate>[0]["patch"], what: string) => bulk.mutate({ ids, patch }, { onSuccess: () => toast.success(`${ids.length} item${ids.length === 1 ? "" : "s"} updated`, what) });
  const archive = () => { if (!confirm(`Archive ${ids.length} item${ids.length === 1 ? "" : "s"}?`)) return; Promise.all(ids.map((id) => del.mutateAsync({ id }))).then(() => { toast.success("Archived", `${ids.length} items moved out of the way.`); onClear(); }); };
  const sel = "h-8 text-xs !w-auto";
  return (
    <div className="fixed bottom-5 left-1/2 -translate-x-1/2 z-40 panel panel-cut px-3 py-2 flex items-center gap-2 flex-wrap animate-pop shadow-2xl border-gold/50" role="toolbar" aria-label="Bulk actions">
      <span className="font-display font-bold text-sm text-gold num mr-1">{ids.length} selected</span>
      <Select className={sel} value="" onChange={(e) => { if (e.target.value !== "") apply({ assignee_id: e.target.value === "none" ? null : e.target.value }, "Assignee changed"); }} aria-label="Assign to"><option value="">Assign…</option><option value="none">Unassigned</option>{(users ?? []).filter((u) => u.is_active).map((u) => <option key={u.id} value={u.id}>{u.emoji} {u.name}</option>)}</Select>
      <Select className={sel} value="" onChange={(e) => { if (e.target.value !== "") apply({ sprint_id: e.target.value === "none" ? null : e.target.value }, "Sprint changed"); }} aria-label="Move to sprint"><option value="">Sprint…</option><option value="none">Backlog</option>{(sprints ?? []).filter((s) => s.state !== "closed").map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select>
      <Select className={sel} value="" onChange={(e) => { if (e.target.value) apply({ priority: e.target.value as Priority }, "Priority changed"); }} aria-label="Set priority"><option value="">Priority…</option>{PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}</Select>
      <span className="inline-flex items-center gap-1" role="group" aria-label="Set points">{scale.map((p) => <button key={p} type="button" onClick={() => apply({ points: p }, `${p} points`)} className={cn("num h-7 min-w-7 px-1.5 rounded-[6px] border border-border text-xs hover:border-teal hover:text-teal")}>{p}</button>)}</span>
      <Button size="sm" variant="danger" icon={Archive} onClick={archive} loading={del.isPending}>Archive</Button>
      <Button size="sm" variant="ghost" icon={X} onClick={onClear} aria-label="Clear selection">Clear</Button>
    </div>
  );
}
