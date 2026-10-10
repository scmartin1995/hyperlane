import { useEffect, useMemo, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Check, Pencil } from "lucide-react";
import type { Project, Sprint, WorkItem } from "@/api/types";
import { fmtDate, pct, priorityIcon, stateOf, typeOf } from "@/lib/format";
import { Avatar, Badge, Button, EmptyState, Progress, Textarea, toast, cn } from "@/components/ui";
import { ChartCard, C, HLLegend, HLTooltip, MARK, axisProps, gridProps } from "@/features/reports/charts";
import { ItemDrawer, LoadingRows } from "./common";
import { sprintDay } from "./SprintDetail";
import { useBurndown, useSprintItems, useUpdateSprint } from "./hooks";

export function SprintOverview({ sprint, project }: { sprint: Sprint; project: Project | undefined }) {
  const { data: items, isLoading } = useSprintItems(sprint.id);
  const { data: burn, isLoading: burnLoading } = useBurndown(sprint.id);
  const [open, setOpen] = useState<string | null>(null);
  const { day, days } = sprintDay(sprint);
  const usePoints = (project?.settings.estimation ?? "points") === "points";
  const byStatus = useMemo(() => {
    const m: Record<string, number> = {};
    (items ?? []).forEach((i) => { m[i.status] = (m[i.status] ?? 0) + 1; });
    return (project?.workflow ?? []).map((s) => ({ state: s, count: m[s.key] ?? 0 })).filter((x) => x.count > 0 || true);
  }, [items, project]);
  const done = (items ?? []).filter((i) => stateOf(project, i.status)?.category === "done");
  const donePts = done.reduce((a, i) => a + (i.points ?? 0), 0), totalPts = (items ?? []).reduce((a, i) => a + (i.points ?? 0), 0);
  const burnRows = (burn ?? []).map((p) => [fmtDate(p.date), p.ideal, p.remaining, p.scope, p.done]);

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <GoalPanel sprint={sprint} />
      <div className="panel p-4 lg:col-span-2 grid grid-cols-2 md:grid-cols-4 gap-3">
        <Tile label={sprint.state === "active" ? "Day" : "Length"} value={sprint.state === "active" ? `${day}/${days}` : `${days}d`} sub={sprint.state === "active" ? `${pct(day, days)}% of time` : `${fmtDate(sprint.start_date)} → ${fmtDate(sprint.end_date)}`} />
        <Tile label="Committed" value={usePoints ? sprint.committed_points || totalPts : sprint.committed_count || items?.length || 0} sub={usePoints ? "points" : "items"} />
        <Tile label="Completed" value={usePoints ? sprint.completed_points || donePts : sprint.completed_count || done.length} sub={`${pct(usePoints ? donePts : done.length, usePoints ? totalPts : items?.length ?? 0)}% of scope`} color={C.green} />
        <Tile label="Items" value={items?.length ?? 0} sub={`${done.length} done`} />
        <div className="col-span-2 md:col-span-4"><Progress value={usePoints ? donePts : done.length} max={(usePoints ? totalPts : items?.length) || 1} color={C.green} height={8} /></div>
      </div>

      <ChartCard className="lg:col-span-2" eyebrow="Burndown" title={usePoints ? "Points remaining" : "Items remaining"} help="Remaining work per day against an ideal straight line; the scope line shows when work was added or removed."
        table={{ columns: ["Date", "Ideal", "Remaining", "Scope", "Done"], rows: burnRows }} empty={!burnLoading && !burn?.length ? "Burndown appears once the sprint has started." : undefined}>
        {burnLoading ? <LoadingRows n={3} /> : (
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={burn ?? []} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="date" tickFormatter={(d: string) => fmtDate(d)} {...axisProps} minTickGap={24} />
              <YAxis {...axisProps} allowDecimals={false} />
              <Tooltip content={<HLTooltip title={(l) => fmtDate(String(l), "EEE, MMM d")} />} cursor={{ stroke: C.grid }} />
              <HLLegend />
              <Area type="monotone" dataKey="scope" name="Scope" stroke={C.gold} fill={C.gold} fillOpacity={MARK.areaOpacity} strokeWidth={1} dot={false} isAnimationActive={false} />
              <Line type="linear" dataKey="ideal" name="Ideal" stroke={C.smoke} strokeWidth={MARK.line} dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="remaining" name="Remaining" stroke={C.teal} strokeWidth={MARK.line} dot={{ r: 3, strokeWidth: 2, stroke: C.surface }} activeDot={{ r: 5 }} />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </ChartCard>

      <section className="panel p-4">
        <div className="eyebrow">By status</div>
        <h2 className="text-base mb-3">Where things stand</h2>
        {byStatus.length === 0 ? <p className="text-sm text-text-3">No workflow states.</p> : (
          <ul className="space-y-2">
            {byStatus.map(({ state, count }) => (
              <li key={state.key} className="flex items-center gap-2 text-sm">
                <span className="w-2 h-2 rounded-full shrink-0" style={{ background: state.color || `var(--cat-${state.category})` }} />
                <span className="flex-1 truncate">{state.name}</span>
                <span className="num text-text-2 w-8 text-right">{count}</span>
                <div className="w-24"><Progress value={count} max={items?.length || 1} color={state.color || `var(--cat-${state.category})`} height={4} /></div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel lg:col-span-3 overflow-hidden">
        <header className="px-4 pt-4 pb-2 flex items-center justify-between"><div><div className="eyebrow">Sprint scope</div><h2 className="text-base">Items in this sprint</h2></div><span className="text-xs text-text-3">{items?.length ?? 0} items · click to open</span></header>
        {isLoading ? <div className="p-4"><LoadingRows /></div> : !items?.length ? (
          <div className="p-4"><EmptyState icon="🧰" title="Nothing committed yet" body="Use the Plan tab to pull work into this sprint." /></div>
        ) : (
          <table className="w-full text-sm">
            <thead><tr className="text-left border-y border-border bg-surface-2/50"><th className="px-4 py-2 eyebrow">Key</th><th className="px-2 py-2 eyebrow">Title</th><th className="px-2 py-2 eyebrow">Status</th><th className="px-2 py-2 eyebrow">Pri</th><th className="px-2 py-2 eyebrow text-right">Pts</th><th className="px-4 py-2 eyebrow">Who</th></tr></thead>
            <tbody>{items.map((it) => <ItemRow key={it.id} item={it} project={project} onClick={() => setOpen(it.id)} />)}</tbody>
          </table>
        )}
      </section>
      <ItemDrawer itemId={open} onClose={() => setOpen(null)} />
    </div>
  );
}

export function ItemRow({ item: it, project, onClick }: { item: WorkItem; project: Project | undefined; onClick: () => void }) {
  const st = stateOf(project, it.status), ty = typeOf(project, it.type);
  return (
    <tr onClick={onClick} className="border-b border-border hover:bg-surface-2/60 cursor-pointer" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onClick()}>
      <td className="px-4 py-2 num text-xs text-text-3 whitespace-nowrap"><span style={{ color: ty?.color }}>{ty?.icon}</span> {it.key}</td>
      <td className="px-2 py-2"><span className={cn(st?.category === "done" && "line-through text-text-3")}>{it.title}</span>{it.blocked && <Badge size="xs" color="var(--rust)" className="ml-2">blocked</Badge>}</td>
      <td className="px-2 py-2"><Badge size="xs" color={st?.color || `var(--cat-${st?.category ?? "todo"})`} dot>{st?.name ?? it.status}</Badge></td>
      <td className="px-2 py-2 text-xs" style={{ color: `var(--prio-${it.priority})` }} title={it.priority}>{priorityIcon[it.priority]}</td>
      <td className="px-2 py-2 num text-right">{it.points ?? "–"}</td>
      <td className="px-4 py-2"><Avatar user={it.assignee} size={22} /></td>
    </tr>
  );
}

function Tile({ label, value, sub, color }: { label: string; value: string | number; sub?: string; color?: string }) {
  return <div><div className="eyebrow">{label}</div><div className="text-2xl font-display font-bold leading-none mt-1" style={{ color }}>{value}</div>{sub && <div className="text-[11px] text-text-3 mt-1">{sub}</div>}</div>;
}

function GoalPanel({ sprint }: { sprint: Sprint }) {
  const [editing, setEditing] = useState(false);
  const [goal, setGoal] = useState(sprint.goal ?? "");
  const update = useUpdateSprint(sprint.id);
  useEffect(() => setGoal(sprint.goal ?? ""), [sprint.goal]);
  const save = () => update.mutate({ goal: goal.trim() || null }, { onSuccess: () => { setEditing(false); toast.success("Goal updated"); }, onError: (e) => toast.error("Couldn't save goal", (e as Error).message) });
  return (
    <section className="panel panel-cut p-4 flex flex-col">
      <div className="hairline mb-3" />
      <div className="flex items-center justify-between"><div className="eyebrow">Sprint goal</div>{!editing && <Button size="xs" variant="ghost" icon={Pencil} onClick={() => setEditing(true)}>Edit</Button>}</div>
      {editing ? (
        <div className="mt-2 space-y-2">
          <Textarea autoFocus value={goal} onChange={(e) => setGoal(e.target.value)} onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") save(); if (e.key === "Escape") setEditing(false); }} placeholder="What does success look like for this sprint?" />
          <div className="flex gap-2 justify-end"><Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button><Button size="sm" variant="primary" icon={Check} loading={update.isPending} onClick={save}>Save</Button></div>
        </div>
      ) : (
        <p className={cn("mt-2 text-base font-display leading-snug flex-1", !sprint.goal && "text-text-3 italic")} onDoubleClick={() => setEditing(true)}>{sprint.goal || "No goal yet. Double-click to set one — teams with a goal finish more."}</p>
      )}
    </section>
  );
}
