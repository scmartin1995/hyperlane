import { createPortal } from "react-dom";
// The Kanban board ("Board"). Columns = project.workflow; dnd-kit drag with optimistic moves.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { DndContext, DragOverlay, KeyboardSensor, PointerSensor, closestCorners, useSensor, useSensors, type DragEndEvent, type DragOverEvent, type DragStartEvent } from "@dnd-kit/core";
import { arrayMove, sortableKeyboardCoordinates } from "@dnd-kit/sortable";
import { Plus, Sparkles } from "lucide-react";
import type { WorkItemInput } from "@/api/types";
import { useMe, useProject, useUsers } from "@/api/queries";
import { useUI, label } from "@/lib/store";
import { stateOf } from "@/lib/format";
import { Button, EmptyState, Kbd, PageHeader, Skeleton, celebrate, cn, toast } from "@/components/ui";
import { useCreateItem, useHotkey, useItems, useLabels, useMoveItem, useSprints } from "@/features/items/hooks";
import { isDone } from "@/features/items/common";
import { ItemDrawer } from "@/features/items/ItemDrawer";
import { CreateItemModal } from "@/features/items/CreateItemModal";
import { CardBody } from "./BoardCard";
import { ColumnBody, ColumnHeader, COL_W } from "./BoardColumn";
import { BoardFilters } from "./BoardFilters";
import { DEFAULT_FILTERS, buildContainers, buildLanes, cid, filterItems, findContainer, hasActiveFilters, parseCid, type BoardFilters as Filters } from "./useBoard";

export default function BoardPage() {
  const ui = useUI();
  const pid = ui.projectId ?? undefined;
  const nav = useNavigate();
  const { data: project } = useProject(pid);
  const { data: me } = useMe();
  const { data: users } = useUsers();
  const { data: labels } = useLabels(pid);
  const { data: sprints } = useSprints(pid);
  const itemsQ = useItems(pid, { include_done: true });
  const move = useMoveItem();
  const create = useCreateItem(pid);

  const [f, setF] = useState<Filters>(DEFAULT_FILTERS);
  const set = useCallback((p: Partial<Filters>) => setF((prev) => ({ ...prev, ...p })), []);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [openId, setOpenId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [local, setLocal] = useState<Record<string, string[]> | null>(null);
  useEffect(() => { setF(DEFAULT_FILTERS); setLocal(null); }, [pid]);
  useHotkey("c", () => setCreateOpen(true), { enabled: !createOpen && !openId });

  const all = useMemo(() => itemsQ.data ?? [], [itemsQ.data]);
  const byId = useMemo(() => new Map(all.map((i) => [i.id, i])), [all]);
  const activeSprint = useMemo(() => sprints?.find((s) => s.state === "active"), [sprints]);
  const filtered = useMemo(() => filterItems(all, f, me?.id, activeSprint?.id), [all, f, me?.id, activeSprint?.id]);
  const lanes = useMemo(() => buildLanes(filtered, all, f.lane, users, project), [filtered, all, f.lane, users, project]);
  const derived = useMemo(() => buildContainers(lanes, project), [lanes, project]);
  const containers = local ?? derived;
  const workflow = project?.workflow ?? [];
  const countByStatus = useMemo(() => { const m: Record<string, number> = {}; for (const k of Object.keys(containers)) { const { status } = parseCid(k); m[status] = (m[status] ?? 0) + containers[k].length; } return m; }, [containers]);
  const pointsByStatus = useMemo(() => { const m: Record<string, number> = {}; for (const i of filtered) m[i.status] = (m[i.status] ?? 0) + (i.points ?? 0); return m; }, [filtered]);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  const onDragStart = (e: DragStartEvent) => { setActiveId(String(e.active.id)); setLocal(derived); };
  const onDragOver = (e: DragOverEvent) => {
    const a = String(e.active.id); const o = e.over ? String(e.over.id) : null; if (!o) return;
    setLocal((prev) => {
      const c = prev ?? derived; const from = findContainer(c, a); const to = c[o] ? o : findContainer(c, o);
      if (!from || !to || from === to || parseCid(from).lane !== parseCid(to).lane) return prev;
      const fromList = c[from].filter((x) => x !== a); const toList = c[to].filter((x) => x !== a);
      const overIdx = toList.indexOf(o); toList.splice(overIdx >= 0 ? overIdx : toList.length, 0, a);
      return { ...c, [from]: fromList, [to]: toList };
    });
  };
  const onDragEnd = (e: DragEndEvent) => {
    const a = String(e.active.id); setActiveId(null);
    const c = local ?? derived; const item = byId.get(a);
    if (!e.over || !item) { setLocal(null); return; }
    const o = String(e.over.id); const cont = findContainer(c, a); if (!cont) { setLocal(null); return; }
    let list = c[cont];
    if (o !== a && list.includes(o)) list = arrayMove(list, list.indexOf(a), list.indexOf(o));
    const idx = list.indexOf(a); const before = list[idx + 1]; const after = list[idx - 1];
    const status = parseCid(cont).status;
    const orderChanged = derived[cont]?.join("|") !== list.join("|");
    if (status === item.status && !orderChanged) { setLocal(null); return; }
    setLocal({ ...c, [cont]: list });
    const wasDone = isDone(project, item.status); const nowDone = isDone(project, status);
    move.mutate({ id: a, move: { ...(status !== item.status ? { status } : {}), ...(before ? { before_id: before } : {}), ...(after ? { after_id: after } : {}) } }, { onSettled: () => setLocal(null) });
    if (!wasDone && nowDone) { celebrate("small"); toast.fun(`${item.key} is done.`, item.title); }
  };

  const quickAdd = (status: string, defaults: Partial<WorkItemInput>) => (title: string) =>
    create.mutateAsync({ title, status, parent_id: defaults.parent_id ?? undefined, assignee_id: defaults.assignee_id ?? undefined, sprint_id: (f.activeOnly ?? !!activeSprint) ? activeSprint?.id : undefined });
  const toggleCol = (k: string) => setCollapsed((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const firstTodo = workflow.find((s) => s.category === "todo")?.key;

  if (!pid) return <EmptyState icon="📋" title="No project yet" body="Create your first project and the board lights up." action={<Button variant="primary" onClick={() => nav("/welcome")}>Run setup</Button>} />;

  return (
    <div className="flex flex-col min-h-[calc(100vh-7.5rem)]">
      <PageHeader eyebrow={ui.flavor ? "Board" : undefined} title={label("board", ui.flavor)} subtitle={activeSprint ? `${activeSprint.name}${activeSprint.goal ? ` · ${activeSprint.goal}` : ""}` : "No active sprint — showing everything. Start one under Sprints."}
        actions={<><Button variant="outline" icon={Sparkles} onClick={() => ui.setAgentOpen(true, { project_id: pid, view: "board" })}>Ask the assistant</Button><Button variant="primary" icon={Plus} onClick={() => setCreateOpen(true)}>New item <Kbd>c</Kbd></Button></>} />
      <BoardFilters f={f} set={set} users={users} labels={labels} project={project} activeSprint={activeSprint} />

      {itemsQ.isLoading ? <div className="flex gap-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-72 w-[272px] shrink-0" />)}</div>
        : all.length === 0 ? <EmptyState icon="🗂️" title="The board is empty" body="Add your first work item, or let the assistant draft a backlog from a paragraph." action={<div className="flex gap-2"><Button variant="primary" icon={Plus} onClick={() => setCreateOpen(true)}>Create an item</Button><Button variant="outline" icon={Sparkles} onClick={() => ui.setAgentOpen(true, { project_id: pid, intent: "build_backlog" })}>Build it with the assistant</Button></div>} />
        : (
          <DndContext sensors={sensors} collisionDetection={closestCorners} onDragStart={onDragStart} onDragOver={onDragOver} onDragEnd={onDragEnd} onDragCancel={() => { setActiveId(null); setLocal(null); }}>
            <div className="overflow-x-auto pb-4 -mx-1 px-1 flex-1">
              <div className="flex gap-3 mb-1 sticky top-0 z-10 bg-bg/80 backdrop-blur py-1 min-w-max">
                {workflow.map((s) => collapsed.has(s.key)
                  ? <div key={s.key} className="w-10" />
                  : <ColumnHeader key={s.key} state={s} count={countByStatus[s.key] ?? 0} points={pointsByStatus[s.key]} collapsed={false} onToggle={() => toggleCol(s.key)} />)}
              </div>
              {filtered.length === 0 && <div className="text-sm text-text-3 py-6 flex items-center gap-2">No cards match these filters.{hasActiveFilters(f) && <Button size="xs" variant="ghost" onClick={() => set({ ...DEFAULT_FILTERS, lane: f.lane })}>Clear filters</Button>}</div>}
              {lanes.map((lane) => (
                <section key={lane.key} className={cn("min-w-max", f.lane !== "none" && "mb-3 panel p-2 pt-1")} aria-label={lane.title}>
                  {f.lane !== "none" && <div className="flex items-center gap-2 h-8 px-1 mb-1"><span className="w-1.5 h-4 rounded-sm" style={{ background: lane.color ?? "var(--smoke)" }} /><span className="font-display font-bold text-sm truncate max-w-[480px]">{lane.title}</span>{lane.subtitle && <span className="num text-[11px] text-text-3">{lane.subtitle}</span>}<span className="num text-[11px] text-text-3 ml-1">{lane.items.length} cards</span></div>}
                  <div className="flex gap-3 items-stretch">
                    {workflow.map((s) => collapsed.has(s.key)
                      ? <ColumnHeader key={s.key} state={s} count={countByStatus[s.key] ?? 0} collapsed onToggle={() => toggleCol(s.key)} />
                      : <ColumnBody key={s.key} containerId={cid(lane.key, s.key)} state={s} ids={containers[cid(lane.key, s.key)] ?? []} byId={byId} project={project} onOpen={setOpenId}
                          onQuickAdd={quickAdd(s.key, lane.defaults)} minHeight={f.lane === "none" ? 320 : 100} />)}
                  </div>
                </section>
              ))}
            </div>
            {createPortal(<DragOverlay dropAnimation={null}>{activeId && byId.get(activeId) ? <div style={{ width: COL_W - 12 }}><CardBody item={byId.get(activeId)!} project={project} overlay /></div> : null}</DragOverlay>, document.body)}
          </DndContext>
        )}

      <ItemDrawer id={openId} onClose={() => setOpenId(null)} />
      <CreateItemModal open={createOpen} onClose={() => setCreateOpen(false)} projectId={pid} defaults={{ status: firstTodo, sprint_id: (f.activeOnly ?? !!activeSprint) ? activeSprint?.id ?? null : null }} onCreated={(it) => { if (stateOf(project, it.status)?.category === "done") celebrate("small"); }} />
    </div>
  );
}
