// My Checklist · private action items. Only ever returned for the current user.
import { useEffect, useMemo, useRef, useState } from "react";
import { DndContext, PointerSensor, KeyboardSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, arrayMove, sortableKeyboardCoordinates, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { Lock, Plus } from "lucide-react";
import type { ActionItem } from "@/api/types";
import { useMyActionItems, useProjects } from "@/api/queries";
import { useUI, label } from "@/lib/store";
import { overdue } from "@/lib/format";
import { Badge, Button, EmptyState, Kbd, PageHeader, Skeleton, Tabs, celebrate, toast } from "@/components/ui";
import { ActionRow } from "./ActionRow";
import { useActionMutations } from "./hooks";
import { parseQuickAdd } from "./parse";

type Filter = "open" | "done" | "overdue" | "snoozed" | "all";

export default function ActionItemsPage() {
  const flavor = useUI((s) => s.flavor);
  const pid = useUI((s) => s.projectId);
  const { data: items, isLoading, isError } = useMyActionItems(true);
  const { data: projects } = useProjects();
  const m = useActionMutations();
  const [filter, setFilter] = useState<Filter>("open");
  const [text, setText] = useState("");
  const [cursor, setCursor] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));
  const now = new Date();
  const isSnoozed = (a: ActionItem) => !!a.snoozed_until && new Date(a.snoozed_until) > now;
  const counts = useMemo(() => ({ open: (items ?? []).filter((a) => !a.done && !isSnoozed(a)).length, done: (items ?? []).filter((a) => a.done).length, overdue: (items ?? []).filter((a) => !a.done && overdue(a.due_date)).length, snoozed: (items ?? []).filter((a) => !a.done && isSnoozed(a)).length, all: items?.length ?? 0 }), [items]); // eslint-disable-line react-hooks/exhaustive-deps
  const list = useMemo(() => (items ?? []).filter((a) => filter === "all" ? true : filter === "done" ? a.done : filter === "overdue" ? !a.done && overdue(a.due_date) : filter === "snoozed" ? !a.done && isSnoozed(a) : !a.done && !isSnoozed(a)), [items, filter]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName; const typing = tag === "INPUT" || tag === "TEXTAREA";
      if (!typing && (e.key === "a" || e.key === "c")) { e.preventDefault(); inputRef.current?.focus(); }
      if (!typing && e.key === "j") setCursor((c) => Math.min(list.length - 1, c + 1));
      if (!typing && e.key === "k") setCursor((c) => Math.max(0, c - 1));
      if (!typing && e.key === "x" && list[cursor]) toggle(list[cursor]);
      if (typing && e.key === "Escape") (e.target as HTMLElement).blur();
    };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  });

  const add = () => {
    const p = parseQuickAdd(text); if (!p.title) return;
    m.create.mutate({ ...p, project_id: pid ?? undefined, source: "web" }, { onSuccess: () => { setText(""); toast.success("Added to your checklist", p.due_date ? `Due ${p.due_date}` : undefined); }, onError: (e) => toast.error("Couldn't add", (e as Error).message) });
  };
  const toggle = (a: ActionItem) => { const done = !a.done; m.update.mutate({ id: a.id, done }, { onError: (e) => toast.error("Couldn't update", (e as Error).message) }); if (done) { celebrate("small"); toast.fun("Done. Nice.", a.title); } };
  const onDragEnd = (e: DragEndEvent) => {
    const { active, over } = e; if (!over || active.id === over.id) return;
    const ids = list.map((a) => a.id); const moved = arrayMove(ids, ids.indexOf(String(active.id)), ids.indexOf(String(over.id)));
    const others = (items ?? []).map((a) => a.id).filter((id) => !ids.includes(id));
    m.reorder.mutate([...moved, ...others], { onError: (er) => toast.error("Couldn't reorder", (er as Error).message) });
  };

  if (isError) return <EmptyState icon="🔒" title="Couldn't load your checklist" body="Sign in with your profile to see private action items." />;
  return (
    <div className="max-w-[920px]">
      <PageHeader eyebrow="Private · Only you" title={label("actionItems", flavor)} subtitle={<span className="inline-flex items-center gap-1.5"><Badge size="xs" color="var(--gold)"><Lock size={10} /> Private — only you can see these</Badge> Your own to-dos, retro actions and things the agent noted for you.</span>}
        actions={<span className="hidden md:inline-flex items-center gap-1 text-xs text-text-3"><Kbd>a</Kbd> add · <Kbd>j</Kbd><Kbd>k</Kbd> move · <Kbd>x</Kbd> done</span>} />
      <form className="flex gap-2 mb-3" onSubmit={(e) => { e.preventDefault(); add(); }}>
        <input ref={inputRef} autoFocus value={text} onChange={(e) => setText(e.target.value)} placeholder="Add a to-do…  try: Book dyno time !high @fri #ops" className="w-full bg-surface-2 border border-border rounded-[8px] px-3 text-base placeholder:text-text-3 focus:border-teal focus:outline-none h-10" aria-label="New action item" />
        <Button type="submit" variant="primary" icon={Plus} loading={m.create.isPending} className="h-10">Add</Button>
      </form>
      <p className="text-[11px] text-text-3 mb-3"><Kbd>!high</Kbd> / <Kbd>!low</Kbd> priority · <Kbd>@tomorrow</Kbd> <Kbd>@fri</Kbd> <Kbd>@3d</Kbd> due · <Kbd>#tag</Kbd></p>
      <Tabs className="mb-3" value={filter} onChange={setFilter} tabs={[{ key: "open", label: "Open", count: counts.open }, { key: "overdue", label: "Overdue", count: counts.overdue }, { key: "snoozed", label: "Snoozed", count: counts.snoozed }, { key: "done", label: "Done", count: counts.done }, { key: "all", label: "All", count: counts.all }]} />
      {isLoading ? <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-10" />)}</div> : list.length === 0 ? (
        <EmptyState icon={filter === "done" ? "🏆" : "✅"} title={filter === "open" ? "Clear track" : `Nothing ${filter}`} body={filter === "open" ? "Nothing on your list. Add one above, or let the agent note things for you." : "Switch filters to see other items."} />
      ) : (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
          <SortableContext items={list.map((a) => a.id)} strategy={verticalListSortingStrategy}>
            <ul className="space-y-1.5">{list.map((a, i) => <ActionRow key={a.id} item={a} projects={projects} focused={i === cursor} onToggle={() => toggle(a)} onPatch={(p) => m.update.mutate({ id: a.id, ...p }, { onError: (e) => toast.error("Couldn't update", (e as Error).message) })} onDelete={() => { if (confirm("Delete this item?")) m.remove.mutate(a.id, { onError: (e) => toast.error("Couldn't delete", (e as Error).message) }); }} />)}</ul>
          </SortableContext>
        </DndContext>
      )}
    </div>
  );
}
