// Column header (name, WIP badge, collapse) and droppable sortable body with quick-add.
import { useState } from "react";
import { useDroppable } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import type { Project, WorkflowState, WorkItem } from "@/api/types";
import { categoryColor } from "@/lib/format";
import { IconButton, Input, cn } from "@/components/ui";
import { BoardCard } from "./BoardCard";

export const COL_W = 272;

export function ColumnHeader({ state, count, collapsed, onToggle, points }: { state: WorkflowState; count: number; collapsed: boolean; onToggle: () => void; points?: number }) {
  const over = state.wip_limit != null && count > state.wip_limit;
  const color = state.color || categoryColor(state.category);
  if (collapsed) return (
    <button type="button" onClick={onToggle} className="h-full w-10 panel flex flex-col items-center gap-2 py-2 hover:border-border-strong" title={`Expand ${state.name}`} aria-label={`Expand ${state.name}`}>
      <ChevronRight size={14} className="text-text-3" />
      <span className="num text-xs font-bold" style={{ color: over ? "var(--rust-light)" : color }}>{count}</span>
      <span className="eyebrow [writing-mode:vertical-rl] rotate-180 text-text-2 whitespace-nowrap">{state.name}</span>
    </button>
  );
  return (
    <div className="flex items-center gap-2 pl-3 pr-1 h-10 rounded-full" style={{ width: COL_W, background: `color-mix(in oklab, ${color} 16%, var(--surface))`, boxShadow: `inset 0 0 0 1px color-mix(in oklab, ${color} 35%, transparent)` }}>
      <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: color }} />
      <span className="font-display font-bold text-[13px] truncate" style={{ color: `color-mix(in oklab, ${color} 70%, var(--text))` }}>{state.name}</span>
      <span className={cn("num text-[11px] font-semibold px-1.5 h-5 inline-flex items-center rounded-full border", over ? "border-rust text-rust-light bg-rust/15 animate-pop" : "border-border text-text-3 bg-surface-2")} title={state.wip_limit != null ? `WIP limit ${state.wip_limit}` : "Cards"}>
        {count}{state.wip_limit != null && <span className="opacity-70">/{state.wip_limit}</span>}
      </span>
      {points != null && points > 0 && <span className="num text-[10px] text-text-3">{points}pt</span>}
      <span className="flex-1" />
      <IconButton size="xs" icon={ChevronLeft} label={`Collapse ${state.name}`} onClick={onToggle} />
    </div>
  );
}

export function ColumnBody({ containerId, state, ids, byId, project, onOpen, onQuickAdd, showQuickAdd = true, minHeight = 120 }: {
  containerId: string; state: WorkflowState; ids: string[]; byId: Map<string, WorkItem>; project: Project | undefined; onOpen: (id: string) => void;
  onQuickAdd?: (title: string) => Promise<unknown> | void; showQuickAdd?: boolean; minHeight?: number;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: containerId, data: { type: "column", status: state.key } });
  const over = state.wip_limit != null && ids.length > state.wip_limit;
  return (
    <div ref={setNodeRef} style={{ width: COL_W, minHeight }} className={cn("flex flex-col gap-2.5 p-2 rounded-[16px] border border-dashed transition-colors", isOver ? "border-purple bg-purple-tint/60" : "border-transparent bg-surface-2/60", over && !isOver && "bg-rust-tint/60")}>
      <SortableContext id={containerId} items={ids} strategy={verticalListSortingStrategy}>
        {ids.map((id) => { const it = byId.get(id); return it ? <BoardCard key={id} item={it} project={project} onOpen={onOpen} /> : null; })}
      </SortableContext>
      {ids.length === 0 && <div className="flex-1 min-h-[60px] rounded-[8px] grid place-items-center text-[11px] text-text-3">Drop here</div>}
      {showQuickAdd && onQuickAdd && <QuickAdd onAdd={onQuickAdd} />}
    </div>
  );
}

function QuickAdd({ onAdd }: { onAdd: (title: string) => Promise<unknown> | void }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const submit = async () => { const t = title.trim(); if (!t) return; setTitle(""); await onAdd(t); };
  if (!open) return <button type="button" onClick={() => setOpen(true)} className="h-8 rounded-[8px] text-xs text-text-3 hover:text-text hover:bg-surface-2 inline-flex items-center gap-1.5 px-2"><Plus size={13} /> Add card</button>;
  return (
    <Input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title, then Enter" aria-label="Quick add card" className="h-8 text-xs"
      onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void submit(); } if (e.key === "Escape") { e.stopPropagation(); setOpen(false); setTitle(""); } }} onBlur={() => { if (!title) setOpen(false); }} />
  );
}
