// Right rail: sprints as drop targets with capacity bars; "Unscheduled" drop target to pull items back.
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useDroppable } from "@dnd-kit/core";
import { Flag, Plus } from "lucide-react";
import { api } from "@/api/client";
import { qk } from "@/api/queries";
import type { Project, Sprint, SprintCapacity, WorkItem } from "@/api/types";
import { fmtDate, pct } from "@/lib/format";
import { useUI, label } from "@/lib/store";
import { Badge, Button, Panel, Progress, Skeleton, cn } from "@/components/ui";
import { isDone, sumPoints } from "@/features/items/common";

export function SprintRail({ project, sprints, items, loading }: { project: Project | undefined; sprints: Sprint[] | undefined; items: WorkItem[]; loading: boolean }) {
  const ui = useUI();
  const open = (sprints ?? []).filter((s) => s.state !== "closed").sort((a, b) => (a.state === "active" ? -1 : b.state === "active" ? 1 : a.number - b.number));
  const unscheduled = items.filter((i) => !i.sprint_id && !isDone(project, i.status));
  return (
    <Panel eyebrow={label("sprints", ui.flavor)} title="Sprint planning" padded={false} className="sticky top-0" actions={<Link to="/sprints" className="no-underline"><Button size="xs" variant="ghost" icon={Plus}>New</Button></Link>}>
      <div className="px-3 pb-3 space-y-2">
        <p className="text-[11px] text-text-3">Drag a story onto a sprint to schedule it.</p>
        {loading && <Skeleton className="h-20" />}
        {!loading && open.length === 0 && <div className="text-xs text-text-3 border border-dashed border-border rounded-[8px] p-3">No planned sprints. <Link to="/sprints">Create one</Link> and it becomes a drop target here.</div>}
        {open.map((s) => <SprintDrop key={s.id} sprint={s} project={project} items={items.filter((i) => i.sprint_id === s.id)} />)}
        <UnscheduledDrop count={unscheduled.length} points={sumPoints(unscheduled)} />
      </div>
    </Panel>
  );
}

function SprintDrop({ sprint, project, items }: { sprint: Sprint; project: Project | undefined; items: WorkItem[] }) {
  const { setNodeRef, isOver } = useDroppable({ id: `sprint:${sprint.id}`, data: { type: "sprint" } });
  const cap = useQuery({ queryKey: qk.sprintCapacity(sprint.id), queryFn: () => api.get<SprintCapacity>(`/sprints/${sprint.id}/capacity`), retry: false, staleTime: 60_000 });
  const usePoints = project?.settings.estimation !== "throughput";
  const load = usePoints ? sumPoints(items) : items.length;
  const done = items.filter((i) => isDone(project, i.status));
  const capacity = cap.data ? (usePoints ? cap.data.team_points : cap.data.team_count) : sprint.capacity_points ?? null;
  const over = capacity != null && capacity > 0 && load > capacity;
  return (
    <div ref={setNodeRef} className={cn("rounded-[10px] border p-2.5 transition-all", isOver ? "border-teal bg-teal/10 scale-[1.02]" : sprint.state === "active" ? "border-gold/50 bg-gold/5" : "border-border bg-surface-2/40")}>
      <div className="flex items-center gap-2">
        <Flag size={13} className={sprint.state === "active" ? "text-gold" : "text-text-3"} />
        <Link to={`/sprints/${sprint.id}`} className="font-display font-semibold text-sm no-underline text-text hover:text-gold truncate">{sprint.name}</Link>
        <Badge size="xs" color={sprint.state === "active" ? "var(--gold)" : undefined}>{sprint.state}</Badge>
        <span className="flex-1" />
        <span className="num text-[10px] text-text-3">{fmtDate(sprint.start_date)}–{fmtDate(sprint.end_date)}</span>
      </div>
      {sprint.goal && <div className="text-[11px] text-text-2 mt-1 line-clamp-2">{sprint.goal}</div>}
      <div className="mt-2 flex items-center justify-between text-[11px]">
        <span className="num"><b className={cn(over && "text-rust-light")}>{load}</b>{capacity != null ? <span className="text-text-3"> / {Math.round(capacity)}</span> : null}{usePoints ? " pts" : " items"} · {items.length} item{items.length === 1 ? "" : "s"}</span>
        <span className="num text-text-3">{done.length} done</span>
      </div>
      <Progress value={load} max={capacity ?? Math.max(load, 1)} color={over ? "var(--rust)" : sprint.state === "active" ? "var(--gold)" : "var(--teal)"} className="mt-1" height={5} />
      {capacity == null && <div className="text-[10px] text-text-3 mt-1">{cap.isLoading ? "Loading capacity…" : "No capacity set — bar shows load only."}</div>}
      {over && <div className="text-[10px] text-rust-light mt-1 font-semibold">{pct(load, capacity ?? 1)}% of capacity — over-committed.</div>}
    </div>
  );
}

function UnscheduledDrop({ count, points }: { count: number; points: number }) {
  const { setNodeRef, isOver } = useDroppable({ id: "sprint:none", data: { type: "sprint" } });
  return (
    <div ref={setNodeRef} className={cn("rounded-[10px] border border-dashed p-2.5 text-xs transition-colors", isOver ? "border-teal bg-teal/10" : "border-border-strong text-text-3")}>
      <div className="flex items-center justify-between"><span className="font-display font-semibold">Unscheduled</span><span className="num">{count} · {points}pt</span></div>
      <div className="text-[10px] mt-0.5">Drop here to pull something out of a sprint.</div>
    </div>
  );
}
