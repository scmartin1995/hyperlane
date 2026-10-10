// Board toolbar: text, assignee chips, type, label, mine, active sprint, swimlanes.
import { Search, X } from "lucide-react";
import type { Label, Project, Sprint, User } from "@/api/types";
import { Avatar, Button, Input, Select, Toggle, cn } from "@/components/ui";
import { DEFAULT_FILTERS, hasActiveFilters, type BoardFilters, type LaneMode } from "./useBoard";

export function BoardFilters({ f, set, users, labels, project, activeSprint }: {
  f: BoardFilters; set: (p: Partial<BoardFilters>) => void; users: User[] | undefined; labels: Label[] | undefined; project: Project | undefined; activeSprint: Sprint | undefined;
}) {
  const activeOnly = f.activeOnly ?? !!activeSprint;
  const toggleAssignee = (id: string) => set({ assignees: f.assignees.includes(id) ? f.assignees.filter((a) => a !== id) : [...f.assignees, id] });
  return (
    <div className="flex flex-wrap items-center gap-2 mb-3">
      <div className="relative"><Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-3" />
        <Input value={f.q} onChange={(e) => set({ q: e.target.value })} placeholder="Filter cards…" aria-label="Filter cards" className="h-8 pl-8 text-xs w-[180px]" /></div>
      <div className="inline-flex items-center -space-x-1" role="group" aria-label="Filter by assignee">
        {(users ?? []).filter((u) => u.is_active).slice(0, 10).map((u) => (
          <button type="button" key={u.id} onClick={() => toggleAssignee(u.id)} aria-pressed={f.assignees.includes(u.id)} title={u.name} className={cn("rounded-full transition-transform hover:scale-110 hover:z-10", f.assignees.includes(u.id) ? "ring-2 ring-teal z-10" : "opacity-80")}><Avatar user={u} size={24} /></button>
        ))}
        <button type="button" onClick={() => toggleAssignee("none")} aria-pressed={f.assignees.includes("none")} title="Unassigned" className={cn("rounded-full ml-1", f.assignees.includes("none") && "ring-2 ring-teal")}><Avatar user={null} size={24} /></button>
      </div>
      <Select value={f.type} onChange={(e) => set({ type: e.target.value })} className="h-8 text-xs !w-auto" aria-label="Type"><option value="">All types</option>{(project?.item_types ?? []).map((t) => <option key={t.key} value={t.key}>{t.icon} {t.plural}</option>)}</Select>
      {!!labels?.length && <Select value={f.label} onChange={(e) => set({ label: e.target.value })} className="h-8 text-xs !w-auto" aria-label="Label"><option value="">All labels</option>{labels.map((l) => <option key={l.id} value={l.name}>{l.name}</option>)}</Select>}
      <Toggle checked={f.mine} onChange={(v) => set({ mine: v })} label={<span className="text-xs">My items</span>} />
      {activeSprint && <Toggle checked={activeOnly} onChange={(v) => set({ activeOnly: v })} label={<span className="text-xs">Active sprint only <span className="text-text-3">· {activeSprint.name}</span></span>} />}
      <span className="flex-1" />
      <label className="inline-flex items-center gap-1.5 text-xs text-text-3">Swimlanes
        <Select value={f.lane} onChange={(e) => set({ lane: e.target.value as LaneMode })} className="h-8 text-xs !w-auto" aria-label="Swimlanes"><option value="none">None</option><option value="epic">By epic</option><option value="assignee">By assignee</option></Select>
      </label>
      {(hasActiveFilters(f) || f.lane !== "none" || f.activeOnly !== null) && <Button size="sm" variant="ghost" icon={X} onClick={() => set({ ...DEFAULT_FILTERS })}>Clear</Button>}
    </div>
  );
}
