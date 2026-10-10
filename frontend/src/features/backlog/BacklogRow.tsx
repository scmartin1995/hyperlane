// One sortable row of the backlog tree, plus the inline create row.
import { useEffect, useState } from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ChevronDown, ChevronRight, GripVertical, Plus, Sparkles, Pencil } from "lucide-react";
import type { Project } from "@/api/types";
import { pct } from "@/lib/format";
import { Avatar, IconButton, Input, cn } from "@/components/ui";
import { BlockedTag, DueChip, LabelChips, PointsChip, PriorityGlyph, StatusBadge, TypeIcon, isDone } from "@/features/items/common";
import type { Row } from "./tree";

export function BacklogRow({ row, project, selected, focused, collapsed, onToggle, onSelect, onOpen, onRename, onAddChild, onAskAgent, canHaveChildren, shiftHeld }: {
  row: Row; project: Project | undefined; selected: boolean; focused: boolean; collapsed: boolean;
  onToggle: () => void; onSelect: (e: React.MouseEvent) => void; onOpen: () => void; onRename: (title: string) => void; onAddChild: () => void; onAskAgent: () => void; canHaveChildren: boolean; shiftHeld: boolean;
}) {
  const n = row.node;
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging, isOver } = useSortable({ id: n.id, data: { type: "row" } });
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(n.title);
  useEffect(() => { if (!editing) setDraft(n.title); }, [n.title, editing]);
  const commit = () => { const t = draft.trim(); if (t && t !== n.title) onRename(t); setEditing(false); };
  const done = isDone(project, n.status);
  const r = row.rollup;
  return (
    <div ref={setNodeRef} style={{ transform: CSS.Translate.toString(transform), transition }} data-row-id={n.id}
      className={cn("group flex items-center gap-1.5 h-10 pr-2 rounded-[8px] border border-transparent text-sm transition-colors", selected ? "bg-teal/10 border-teal/40" : "hover:bg-surface-2", focused && "ring-1 ring-gold/60", isDragging && "opacity-40", isOver && shiftHeld && "border-purple-light bg-purple/15")}>
      <span ref={setActivatorNodeRef} {...attributes} {...listeners} className="cursor-grab active:cursor-grabbing text-text-3 opacity-0 group-hover:opacity-100 focus:opacity-100 px-1" aria-label={`Drag ${n.key}`}><GripVertical size={14} /></span>
      <input type="checkbox" checked={selected} onChange={() => undefined} onClick={onSelect} aria-label={`Select ${n.key}`} className="accent-[var(--teal)] cursor-pointer" />
      <span style={{ width: row.depth * 22 }} className="shrink-0" aria-hidden />
      {row.hasChildren ? <button type="button" onClick={onToggle} aria-label={collapsed ? "Expand" : "Collapse"} aria-expanded={!collapsed} className="w-5 h-5 grid place-items-center text-text-3 hover:text-text rounded">{collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}</button> : <span className="w-5" />}
      <TypeIcon project={project} type={n.type} />
      <span className="num text-[11px] text-text-3 w-14 shrink-0">{n.key}</span>
      {editing ? (
        <Input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} onBlur={commit} aria-label="Rename" className="h-7 text-sm flex-1 min-w-0" onKeyDown={(e) => { if (e.key === "Enter") commit(); if (e.key === "Escape") { e.stopPropagation(); setEditing(false); } }} />
      ) : (
        <button type="button" onClick={onOpen} onDoubleClick={(e) => { e.preventDefault(); setEditing(true); }} className={cn("flex-1 min-w-0 text-left truncate", done && "line-through text-text-3")} title="Click to open · double-click to rename">{n.title}</button>
      )}
      <span className="inline-flex items-center gap-1.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 shrink-0">
        <IconButton size="xs" icon={Pencil} label="Rename" onClick={() => setEditing(true)} />
        {canHaveChildren && <IconButton size="xs" icon={Plus} label="Add child" onClick={onAddChild} />}
        {row.depth === 0 && <IconButton size="xs" icon={Sparkles} label="Ask the agent to build this out" onClick={onAskAgent} className="text-gold" />}
      </span>
      {n.blocked && <BlockedTag reason={n.blocked_reason} />}
      <LabelChips labels={n.labels} max={2} />
      {row.hasChildren && (
        <span className="inline-flex items-center gap-1.5 shrink-0" title={`${r.done}/${r.total} done · ${r.donePoints}/${r.points} pts`}>
          <span className="w-16 h-1.5 rounded-full bg-surface-3 overflow-hidden"><span className="block h-full bg-green rounded-full" style={{ width: `${pct(r.done, r.total)}%` }} /></span>
          <span className="num text-[10px] text-text-3">{pct(r.done, r.total)}% · {r.points}pt</span>
        </span>
      )}
      <DueChip due={n.due_date} done={done} />
      <PriorityGlyph priority={n.priority} />
      <PointsChip points={n.points} />
      <StatusBadge project={project} status={n.status} />
      <Avatar user={n.assignee} size={20} />
    </div>
  );
}

export function CreateRow({ depth, typeName, onCreate, onClose }: { depth: number; typeName: string; onCreate: (title: string) => Promise<unknown>; onClose: () => void }) {
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => { const t = title.trim(); if (!t) return; setBusy(true); try { await onCreate(t); setTitle(""); } finally { setBusy(false); } };
  return (
    <div className="flex items-center gap-1.5 h-10 pl-9 pr-2 animate-in">
      <span style={{ width: depth * 22 }} className="shrink-0" aria-hidden />
      <Plus size={14} className="text-teal" />
      <Input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} disabled={busy} placeholder={`New ${typeName} — Enter to add another, Esc to stop`} aria-label={`New ${typeName}`} className="h-8 text-sm"
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void submit(); } if (e.key === "Escape") { e.stopPropagation(); onClose(); } }} onBlur={() => { if (!title) onClose(); }} />
    </div>
  );
}
