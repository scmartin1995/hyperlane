import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { AlarmClock, ChevronDown, ChevronRight, GripVertical, Trash2 } from "lucide-react";
import { addDays, format } from "date-fns";
import type { ActionItem, Priority, Project } from "@/api/types";
import { fmtDate, overdue, priorityIcon } from "@/lib/format";
import { Badge, Button, IconButton, Menu, Textarea, cn } from "@/components/ui";
import { parseDue } from "./parse";

const SOURCE_COLOR: Record<string, string> = { retro: "var(--purple-light)", agent: "var(--teal)", slack: "var(--gold)" };
const PRIOS: Priority[] = ["critical", "high", "medium", "low", "none"];

export function ActionRow({ item: a, projects, onToggle, onPatch, onDelete, focused }: { item: ActionItem; projects: Project[] | undefined; onToggle: () => void; onPatch: (p: Partial<ActionItem>) => void; onDelete: () => void; focused: boolean }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: a.id });
  const [editing, setEditing] = useState(false); const [title, setTitle] = useState(a.title);
  const [open, setOpen] = useState(false);
  const [notes, setNotes] = useState(a.notes ?? ""); const [saved, setSaved] = useState<"idle" | "saving" | "saved">("idle");
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => setTitle(a.title), [a.title]); useEffect(() => setNotes(a.notes ?? ""), [a.notes]);
  useEffect(() => { if (editing) inputRef.current?.select(); }, [editing]);
  const commitTitle = () => { setEditing(false); if (title.trim() && title.trim() !== a.title) onPatch({ title: title.trim() }); else setTitle(a.title); };
  const saveNotes = () => { if ((a.notes ?? "") === notes) return; setSaved("saving"); onPatch({ notes: notes || null }); setTimeout(() => { setSaved("saved"); setTimeout(() => setSaved("idle"), 1500); }, 300); };
  const isOver = !a.done && overdue(a.due_date);
  const snoozed = a.snoozed_until && new Date(a.snoozed_until) > new Date();
  const project = projects?.find((p) => p.id === a.project_id);
  const snoozeOpts = [["Tomorrow", 1], ["In 3 days", 3], ["Next week", 7]] as const;
  return (
    <li ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }} className={cn("panel px-2 py-1.5 animate-in", isDragging && "opacity-60 shadow-2xl z-10", focused && "border-gold", a.done && "opacity-60")}>
      <div className="flex items-center gap-2">
        <button {...attributes} {...listeners} className="text-text-3 hover:text-text cursor-grab active:cursor-grabbing touch-none" aria-label="Drag to reorder"><GripVertical size={14} /></button>
        <input type="checkbox" checked={a.done} onChange={onToggle} className="w-4 h-4 accent-[var(--green)]" aria-label={a.done ? "Mark not done" : "Mark done"} />
        <span className="text-xs w-4 text-center" style={{ color: `var(--prio-${a.priority})` }} title={`Priority: ${a.priority}`}>{priorityIcon[a.priority]}</span>
        {editing ? (
          <input ref={inputRef} value={title} onChange={(e) => setTitle(e.target.value)} onBlur={commitTitle} onKeyDown={(e) => { if (e.key === "Enter") commitTitle(); if (e.key === "Escape") { setTitle(a.title); setEditing(false); } }} className="flex-1 bg-transparent border-b border-teal outline-none text-sm px-1" />
        ) : (
          <button onClick={() => setEditing(true)} className={cn("flex-1 text-left text-sm truncate px-1 rounded hover:bg-surface-2", a.done && "line-through text-text-3")} title="Click to edit">{a.title}</button>
        )}
        <div className="flex items-center gap-1 shrink-0 flex-wrap justify-end">
          {a.tags.map((t) => <Badge key={t} size="xs">#{t}</Badge>)}
          {a.work_item_id && <Link to={`/items/${a.work_item_id}`} className="text-[11px] num no-underline hover:underline">{String(a.source_ref ?? "item")} ↗</Link>}
          {project && <Badge size="xs" color={project.color}>{project.key}</Badge>}
          {a.source && a.source !== "web" && a.source !== "manual" && <Badge size="xs" color={SOURCE_COLOR[a.source]}>{a.source}</Badge>}
          {snoozed && <Badge size="xs" color="var(--smoke)"><AlarmClock size={10} /> until {fmtDate(a.snoozed_until)}</Badge>}
          <label className={cn("inline-flex items-center h-[18px] px-1.5 rounded-full border text-[10px] font-display font-semibold cursor-pointer", isOver ? "border-rust text-rust-light bg-rust/10" : a.due_date ? "border-border text-text-2" : "border-dashed border-border-strong text-text-3")} title="Due date">
            {a.due_date ? fmtDate(a.due_date) : "due"}<input type="date" className="sr-only" value={a.due_date ?? ""} onChange={(e) => onPatch({ due_date: e.target.value || null })} />
          </label>
          <Menu align="right" trigger={<IconButton icon={AlarmClock} label="Snooze" size="xs" />} items={[
            ...snoozeOpts.map(([l, d]) => ({ label: l, onClick: () => onPatch({ snoozed_until: format(addDays(new Date(), d), "yyyy-MM-dd") }) })),
            { label: "Until Monday", onClick: () => onPatch({ snoozed_until: parseDue("mon") }) },
            { label: "Unsnooze", onClick: () => onPatch({ snoozed_until: null }), disabled: !a.snoozed_until },
          ]} />
          <Menu align="right" trigger={<Button size="xs" variant="ghost" aria-label="Priority">{priorityIcon[a.priority]}</Button>} items={PRIOS.map((p) => ({ label: `${priorityIcon[p]} ${p}`, onClick: () => onPatch({ priority: p }) }))} />
          <IconButton icon={open ? ChevronDown : ChevronRight} label={open ? "Hide notes" : "Show notes"} size="xs" onClick={() => setOpen((o) => !o)} className={cn(a.notes && !open && "text-teal")} />
          <IconButton icon={Trash2} label="Delete" size="xs" onClick={onDelete} className="hover:text-rust-light" />
        </div>
      </div>
      {open && (
        <div className="mt-2 ml-9 mr-1 animate-in">
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} onBlur={saveNotes} placeholder="Notes (markdown). Autosaves when you click away." className="min-h-[70px] text-xs" />
          <div className="text-[10px] text-text-3 text-right h-4">{saved === "saving" ? "Saving…" : saved === "saved" ? "Saved ✓" : ""}</div>
        </div>
      )}
    </li>
  );
}
