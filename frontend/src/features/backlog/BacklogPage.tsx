// Hierarchical backlog ("Backlog"): tree with drag reorder/re-parent, sprint rail drop targets, bulk actions, list view.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { DndContext, DragOverlay, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { ChevronsDownUp, ChevronsUpDown, List, ListTree, Plus, Search, Sparkles } from "lucide-react";
import type { WorkItemTreeNode } from "@/api/types";
import { qk, useMe, useProject, useUsers } from "@/api/queries";
import { useUI, label } from "@/lib/store";
import { Button, EmptyState, Input, Kbd, PageHeader, Skeleton, Tabs, Toggle, cn, toast } from "@/components/ui";
import { useCreateItem, useHotkey, useItemTree, useItems, useMoveItem, useSprints, useUpdateItem } from "@/features/items/hooks";
import { TypeIcon, childTypeOf, descendantIds, findNode, typesByLevel } from "@/features/items/common";
import { ItemDrawer } from "@/features/items/ItemDrawer";
import { CreateItemModal } from "@/features/items/CreateItemModal";
import { BacklogRow, CreateRow } from "./BacklogRow";
import { SprintRail } from "./SprintRail";
import { BulkBar } from "./BulkBar";
import { TriagePanel } from "./TriagePanel";
import { ListView } from "./ListView";
import { computeRollups, flatten, insertionIndex, moveNode } from "./tree";

export default function BacklogPage() {
  const ui = useUI();
  const pid = ui.projectId ?? undefined;
  const nav = useNavigate();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const { data: project } = useProject(pid);
  const { data: me } = useMe();
  const { data: users } = useUsers();
  const { data: sprints, isLoading: sprintsLoading } = useSprints(pid);
  const treeQ = useItemTree(pid);
  const flatQ = useItems(pid, { include_done: true });
  const move = useMoveItem();
  const update = useUpdateItem();
  const create = useCreateItem(pid);

  const [view, setView] = useState<"tree" | "list">("tree");
  const [q, setQ] = useState("");
  const [hideDone, setHideDone] = useState(true);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [lastClick, setLastClick] = useState<string | null>(null);
  const [focus, setFocus] = useState<number>(-1);
  const [openId, setOpenId] = useState<string | null>(null);
  const [creating, setCreating] = useState<{ parentId: string | null } | null>(null);
  const [createOpen, setCreateOpen] = useState(params.get("new") === "1");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [shift, setShift] = useState(false);
  const shiftRef = useRef(false);
  useEffect(() => { setSelected(new Set()); setCollapsed(new Set()); setCreating(null); }, [pid]);
  useEffect(() => { if (params.get("new") === "1") { setCreateOpen(true); params.delete("new"); setParams(params, { replace: true }); } }, [params, setParams]);
  useEffect(() => { const d = (e: KeyboardEvent) => { if (e.key === "Shift") { shiftRef.current = true; setShift(true); } }; const u = (e: KeyboardEvent) => { if (e.key === "Shift") { shiftRef.current = false; setShift(false); } }; window.addEventListener("keydown", d); window.addEventListener("keyup", u); return () => { window.removeEventListener("keydown", d); window.removeEventListener("keyup", u); }; }, []);

  const tree = useMemo(() => treeQ.data ?? [], [treeQ.data]);
  const rollups = useMemo(() => computeRollups(tree, project), [tree, project]);
  const rows = useMemo(() => flatten(tree, collapsed, rollups, q, hideDone, project), [tree, collapsed, rollups, q, hideDone, project]);
  const rowIds = useMemo(() => rows.map((r) => r.node.id), [rows]);
  const lowestLevel = useMemo(() => Math.max(0, ...(project?.item_types.map((t) => t.level) ?? [0])), [project]);
  const levelOf = (type: string) => project?.item_types.find((t) => t.key === type)?.level ?? lowestLevel;
  const typeName = (key: string) => project?.item_types.find((t) => t.key === key)?.name ?? key;

  useHotkey("c", () => setCreateOpen(true), { enabled: !createOpen && !openId && !creating });
  useHotkey("ArrowDown", (e) => { e.preventDefault(); setFocus((f) => Math.min(rows.length - 1, f + 1)); }, { enabled: view === "tree" && !openId });
  useHotkey("ArrowUp", (e) => { e.preventDefault(); setFocus((f) => Math.max(0, f - 1)); }, { enabled: view === "tree" && !openId });
  useHotkey("Enter", () => { const r = rows[focus]; if (r) setOpenId(r.node.id); }, { enabled: view === "tree" && focus >= 0 && !openId && !createOpen });
  useHotkey(" ", (e) => { const r = rows[focus]; if (r) { e.preventDefault(); toggleSelect(r.node.id, false); } }, { enabled: view === "tree" && focus >= 0 && !openId });
  useHotkey("Escape", () => { if (selected.size) setSelected(new Set()); else setFocus(-1); }, { enabled: !openId && !createOpen && !creating });
  useEffect(() => { if (focus >= 0) document.querySelector<HTMLElement>(`[data-row-id="${rows[focus]?.node.id}"]`)?.scrollIntoView({ block: "nearest" }); }, [focus, rows]);

  const toggleSelect = useCallback((id: string, range: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (range && lastClick) {
        const a = rowIds.indexOf(lastClick), b = rowIds.indexOf(id);
        if (a >= 0 && b >= 0) { for (let i = Math.min(a, b); i <= Math.max(a, b); i++) next.add(rowIds[i]); return next; }
      }
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
    setLastClick(id);
  }, [lastClick, rowIds]);
  const toggleCollapse = (id: string) => setCollapsed((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const collapseAll = () => setCollapsed(new Set(rows.filter((r) => r.hasChildren).map((r) => r.node.id)));
  const setTreeLocal = (next: WorkItemTreeNode[]) => qc.setQueriesData<WorkItemTreeNode[]>({ queryKey: qk.itemTree(pid ?? "") }, () => next);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));
  const onDragEnd = (e: DragEndEvent) => {
    setActiveId(null);
    const a = String(e.active.id); const o = e.over ? String(e.over.id) : null;
    if (!o || a === o) return;
    const src = findNode(tree, a); if (!src) return;
    if (o.startsWith("sprint:")) {
      const sid = o.slice(7) === "none" ? null : o.slice(7);
      const ids = selected.has(a) ? [...selected] : [a];
      ids.forEach((id) => move.mutate({ id, move: { sprint_id: sid } }));
      toast.fun(sid ? `Scheduled ${ids.length === 1 ? src.key : `${ids.length} items`}.` : `Back to the backlog.`, sid ? sprints?.find((s) => s.id === sid)?.name : undefined);
      return;
    }
    const tgt = findNode(tree, o); if (!tgt) return;
    if (descendantIds(src).includes(o)) { toast.error("Can't nest an item inside its own child."); return; }
    if (shiftRef.current) {
      if (levelOf(tgt.type) >= lowestLevel) { toast.error(`${typeName(tgt.type)} items can't have children.`); return; }
      setTreeLocal(moveNode(tree, a, { parentId: o }));
      setCollapsed((s) => { const n = new Set(s); n.delete(o); return n; });
      move.mutate({ id: a, move: { parent_id: o } }, { onSuccess: () => toast.success(`${src.key} nested under ${tgt.key}`) });
      return;
    }
    const srcIdx = rowIds.indexOf(a), tgtIdx = rowIds.indexOf(o);
    const after = srcIdx < tgtIdx;
    const parentId = tgt.parent_id ?? null;
    setTreeLocal(moveNode(tree, a, after ? { parentId, afterId: o } : { parentId, beforeId: o }));
    move.mutate({ id: a, move: { ...(parentId !== (src.parent_id ?? null) ? { parent_id: parentId } : {}), ...(after ? { after_id: o } : { before_id: o }) } });
  };

  const startCreate = (parentId: string | null) => { if (parentId) setCollapsed((s) => { const n = new Set(s); n.delete(parentId); return n; }); setCreating({ parentId }); };
  const createChild = async (parentId: string | null, title: string) => {
    const parent = parentId ? findNode(tree, parentId) : undefined;
    const type = parent ? childTypeOf(project, parent.type) : typesByLevel(project)[0]?.key;
    await create.mutateAsync({ title, type, parent_id: parentId, sprint_id: parent?.sprint_id ?? undefined });
  };
  const createIdx = creating ? insertionIndex(rows, creating.parentId) : -1;
  const createType = creating ? (creating.parentId ? childTypeOf(project, findNode(tree, creating.parentId)?.type) : typesByLevel(project)[0]?.key ?? "") : "";
  const createDepth = creating?.parentId ? (rows.find((r) => r.node.id === creating.parentId)?.depth ?? 0) + 1 : 0;
  const askAgent = (id: string) => { const n = findNode(tree, id); ui.setAgentOpen(true, { item_id: id, item_key: n?.key, project_id: pid, intent: "build_out" }); };

  if (!pid) return <EmptyState icon="🏁" title="No project yet" body="The backlog lives inside a project. Create one to start stacking epics." action={<Button variant="primary" onClick={() => nav("/welcome")}>Run setup</Button>} />;
  const activeNode = activeId ? findNode(tree, activeId) : null;

  return (
    <div>
      <PageHeader eyebrow={ui.flavor ? "Backlog" : undefined} title={label("backlog", ui.flavor)} subtitle={`${typesByLevel(project).map((t) => t.plural).join(" → ")} · drag to reorder, hold Shift while dropping to nest`}
        actions={<><Button variant="outline" icon={Sparkles} onClick={() => ui.setAgentOpen(true, { project_id: pid, intent: "build_backlog" })}>Build with the assistant</Button><Button variant="primary" icon={Plus} onClick={() => setCreateOpen(true)}>New item <Kbd>c</Kbd></Button></>} />
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <Tabs value={view} onChange={setView} tabs={[{ key: "tree", label: <span className="inline-flex items-center gap-1"><ListTree size={13} />Tree</span> }, { key: "list", label: <span className="inline-flex items-center gap-1"><List size={13} />List</span> }]} />
        <div className="relative"><Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-3" /><Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search key or title…" aria-label="Search backlog" className="h-8 pl-8 text-xs w-[220px]" /></div>
        <Toggle checked={hideDone} onChange={setHideDone} label={<span className="text-xs">Hide done</span>} />
        {view === "tree" && <><Button size="xs" variant="ghost" icon={ChevronsDownUp} onClick={collapseAll}>Collapse all</Button><Button size="xs" variant="ghost" icon={ChevronsUpDown} onClick={() => setCollapsed(new Set())}>Expand all</Button></>}
        <span className="flex-1" />
        <span className="text-[11px] text-text-3 hidden lg:inline-flex items-center gap-1"><Kbd>↑</Kbd><Kbd>↓</Kbd> move · <Kbd>↵</Kbd> open · <Kbd>space</Kbd> select · shift-click for ranges</span>
      </div>

      <TriagePanel project={project} sprints={sprints ?? []} onOpen={setOpenId} />
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_300px] gap-4 items-start">
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragStart={(e) => setActiveId(String(e.active.id))} onDragEnd={onDragEnd} onDragCancel={() => setActiveId(null)}>
          <div className="panel p-2 min-h-[300px]">
            {view === "list" ? (
              <ListView items={flatQ.data ?? []} project={project} sprints={sprints} q={q} loading={flatQ.isLoading} selected={selected} onSelect={(id, e) => toggleSelect(id, e.shiftKey)} onOpen={setOpenId} />
            ) : treeQ.isLoading ? <div className="space-y-2 p-2">{[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-9" />)}</div>
              : tree.length === 0 ? (
                <EmptyState icon="🗂️" title="The backlog is empty" body="Start with an epic, or describe the product in a paragraph and let the assistant draft the whole tree." action={<div className="flex gap-2"><Button variant="primary" icon={Plus} onClick={() => startCreate(null)}>Add the first {typeName(typesByLevel(project)[0]?.key ?? "epic")}</Button><Button variant="outline" icon={Sparkles} onClick={() => ui.setAgentOpen(true, { project_id: pid, intent: "build_backlog" })}>Build with the assistant</Button></div>} />
              ) : (
                <SortableContext items={rowIds} strategy={verticalListSortingStrategy}>
                  <div role="tree" aria-label="Backlog tree">
                    {rows.map((r, i) => (
                      <div key={r.node.id}>
                        {creating && createIdx === i && <CreateRow depth={createDepth} typeName={typeName(createType)} onCreate={(t) => createChild(creating.parentId, t)} onClose={() => setCreating(null)} />}
                        <BacklogRow row={r} project={project} selected={selected.has(r.node.id)} focused={focus === i} collapsed={collapsed.has(r.node.id)} shiftHeld={shift && !!activeId}
                          onToggle={() => toggleCollapse(r.node.id)} onSelect={(e) => toggleSelect(r.node.id, e.shiftKey)} onOpen={() => setOpenId(r.node.id)}
                          onRename={(t) => update.mutate({ id: r.node.id, patch: { title: t } })} onAddChild={() => startCreate(r.node.id)} onAskAgent={() => askAgent(r.node.id)} canHaveChildren={levelOf(r.node.type) < lowestLevel} />
                      </div>
                    ))}
                    {creating && createIdx >= rows.length && <CreateRow depth={createDepth} typeName={typeName(createType)} onCreate={(t) => createChild(creating.parentId, t)} onClose={() => setCreating(null)} />}
                    {!creating && rows.length > 0 && <button type="button" onClick={() => startCreate(null)} className="w-full h-9 mt-1 rounded-[8px] text-xs text-text-3 hover:text-text hover:bg-surface-2 inline-flex items-center gap-1.5 px-3"><Plus size={13} /> Add {typeName(typesByLevel(project)[0]?.key ?? "epic")}</button>}
                    {rows.length === 0 && <div className="py-8 text-center text-sm text-text-3">Nothing matches “{q}”.</div>}
                  </div>
                </SortableContext>
              )}
          </div>
          <SprintRail project={project} sprints={sprints} items={flatQ.data ?? []} loading={sprintsLoading} />
          <DragOverlay dropAnimation={null}>
            {activeNode && <div className={cn("panel px-3 py-2 flex items-center gap-2 text-sm glow-teal", shift && "border-purple-light")}><TypeIcon project={project} type={activeNode.type} /><span className="num text-xs text-text-3">{activeNode.key}</span><span className="truncate max-w-[320px]">{activeNode.title}</span>{selected.has(activeNode.id) && selected.size > 1 && <span className="num text-[10px] bg-teal text-ink rounded-full px-1.5">+{selected.size - 1}</span>}{shift && <span className="text-[10px] text-purple-light font-display uppercase">nest</span>}</div>}
          </DragOverlay>
        </DndContext>
      </div>

      <BulkBar ids={[...selected]} project={project} users={users} sprints={sprints} onClear={() => setSelected(new Set())} />
      <ItemDrawer id={openId} onClose={() => setOpenId(null)} />
      <CreateItemModal open={createOpen} onClose={() => setCreateOpen(false)} projectId={pid} defaults={{ assignee_id: me?.id ?? null }} />
    </div>
  );
}
