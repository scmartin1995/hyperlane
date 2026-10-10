// Searchable parent picker + label picker, reused by ItemDetail and CreateItemModal.
import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Plus, Search, X } from "lucide-react";
import type { Label, Project, WorkItem } from "@/api/types";
import { Badge, Input, cn } from "@/components/ui";
import { useItems, useLabels } from "./hooks";
import { TypeIcon } from "./common";

export function ParentPicker({ project, value, onChange, excludeIds = [], placeholder = "No parent", className }: {
  project: Project | undefined; value: string | null; onChange: (id: string | null) => void; excludeIds?: string[]; placeholder?: string; className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const { data: items } = useItems(project?.id, { include_done: true });
  const ex = useMemo(() => new Set(excludeIds), [excludeIds]);
  const maxLevel = useMemo(() => Math.max(0, ...(project?.item_types.map((t) => t.level) ?? [0])), [project]);
  const options = useMemo(() => {
    const term = q.trim().toLowerCase();
    return (items ?? [])
      .filter((i) => !ex.has(i.id))
      .filter((i) => { const t = project?.item_types.find((x) => x.key === i.type); return !t || t.level < maxLevel; })
      .filter((i) => !term || i.title.toLowerCase().includes(term) || i.key.toLowerCase().includes(term))
      .slice(0, 40);
  }, [items, ex, q, project, maxLevel]);
  const current = items?.find((i) => i.id === value);
  useEffect(() => { if (!open) return; const h = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); }; window.addEventListener("mousedown", h); return () => window.removeEventListener("mousedown", h); }, [open]);
  useEffect(() => setIdx(0), [q, open]);
  const pick = (it: WorkItem | null) => { onChange(it?.id ?? null); setOpen(false); setQ(""); };
  return (
    <div className={cn("relative", className)} ref={ref}>
      <button type="button" onClick={() => setOpen((o) => !o)} aria-haspopup="listbox" aria-expanded={open} className="w-full h-9 px-3 flex items-center gap-2 bg-surface-2 border border-border rounded-[8px] text-sm text-left hover:border-border-strong focus:border-teal">
        {current ? <><TypeIcon project={project} type={current.type} /><span className="num text-xs text-text-3">{current.key}</span><span className="truncate flex-1">{current.title}</span></> : <span className="text-text-3 flex-1">{placeholder}</span>}
        {current && <span role="button" aria-label="Clear parent" onClick={(e) => { e.stopPropagation(); pick(null); }} className="text-text-3 hover:text-text"><X size={13} /></span>}
        <ChevronDown size={14} className="text-text-3" />
      </button>
      {open && (
        <div className="absolute z-40 left-0 right-0 mt-1 panel p-1 animate-pop max-h-72 flex flex-col">
          <div className="relative p-1"><Search size={13} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-3" />
            <Input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by key or title…" className="h-8 pl-8 text-xs"
              onKeyDown={(e) => { if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(options.length - 1, i + 1)); } else if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(0, i - 1)); } else if (e.key === "Enter") { e.preventDefault(); if (options[idx]) pick(options[idx]); } else if (e.key === "Escape") { e.stopPropagation(); setOpen(false); } }} />
          </div>
          <div role="listbox" className="overflow-y-auto">
            <button type="button" onClick={() => pick(null)} className="w-full flex items-center gap-2 px-2.5 h-8 rounded-[6px] text-left text-sm text-text-3 hover:bg-surface-2">{placeholder}</button>
            {options.map((it, i) => (
              <button type="button" key={it.id} role="option" aria-selected={it.id === value} onMouseEnter={() => setIdx(i)} onClick={() => pick(it)} className={cn("w-full flex items-center gap-2 px-2.5 h-8 rounded-[6px] text-left text-sm", i === idx ? "bg-surface-2" : "hover:bg-surface-2")}>
                <TypeIcon project={project} type={it.type} /><span className="num text-xs text-text-3">{it.key}</span><span className="truncate flex-1">{it.title}</span>{it.id === value && <Check size={13} className="text-gold" />}
              </button>
            ))}
            {!options.length && <div className="px-3 py-4 text-xs text-text-3">No matching parent. Epics and features show up here once they exist.</div>}
          </div>
        </div>
      )}
    </div>
  );
}

/** Multi-select over the project's labels; typing a new name + Enter creates it on save (labels are sent as names). */
export function LabelPicker({ projectId, value, onChange, className }: { projectId: string | undefined; value: string[]; onChange: (names: string[]) => void; className?: string }) {
  const { data: labels } = useLabels(projectId);
  const [draft, setDraft] = useState("");
  const all: Label[] = labels ?? [];
  const toggle = (name: string) => onChange(value.includes(name) ? value.filter((v) => v !== name) : [...value, name]);
  const add = () => { const n = draft.trim(); if (!n) return; if (!value.includes(n)) onChange([...value, n]); setDraft(""); };
  const custom = value.filter((v) => !all.some((l) => l.name === v));
  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      {all.map((l) => <Badge key={l.id} size="xs" color={value.includes(l.name) ? l.color || "var(--gold)" : undefined} onClick={() => toggle(l.name)} className={cn(!value.includes(l.name) && "opacity-70")}>{value.includes(l.name) && <Check size={10} />}{l.name}</Badge>)}
      {custom.map((n) => <Badge key={n} size="xs" color="var(--gold)" onClick={() => toggle(n)}><Check size={10} />{n}</Badge>)}
      <span className="inline-flex items-center gap-1">
        <input value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} placeholder="new label…" aria-label="New label" className="h-[22px] w-24 px-2 text-[11px] bg-transparent border border-dashed border-border-strong rounded-full focus:border-teal focus:outline-none" />
        {draft && <button type="button" onClick={add} aria-label="Add label" className="text-teal"><Plus size={13} /></button>}
      </span>
    </div>
  );
}
