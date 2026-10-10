// Children of an item with progress + quick-add (Enter chains).
import { useState } from "react";
import { Plus } from "lucide-react";
import type { Project, WorkItem } from "@/api/types";
import { pct } from "@/lib/format";
import { Avatar, Input, Progress, cn } from "@/components/ui";
import { useCreateItem } from "./hooks";
import { PointsChip, StatusBadge, TypeIcon, childTypeOf, isDone } from "./common";

export function ItemChildren({ parent, project, children, onOpen }: { parent: WorkItem; project: Project | undefined; children: WorkItem[]; onOpen: (id: string) => void }) {
  const create = useCreateItem(project?.id);
  const [title, setTitle] = useState("");
  const [adding, setAdding] = useState(false);
  const done = children.filter((c) => isDone(project, c.status)).length;
  const childType = childTypeOf(project, parent.type);
  const typeName = project?.item_types.find((t) => t.key === childType)?.name ?? "child";
  const submit = () => {
    const t = title.trim(); if (!t) return;
    create.mutate({ title: t, type: childType, parent_id: parent.id, sprint_id: parent.sprint_id ?? undefined }, { onSuccess: () => setTitle("") });
  };
  return (
    <section>
      <div className="flex items-center justify-between mb-1.5">
        <span className="eyebrow">Children <span className="num">{done}/{children.length}</span></span>
        {children.length > 0 && <span className="num text-[11px] text-text-3">{pct(done, children.length)}%</span>}
      </div>
      {children.length > 0 && <Progress value={done} max={children.length} color="var(--green)" className="mb-2" height={4} />}
      <ul className="divide-y divide-border rounded-[8px] border border-border overflow-hidden">
        {children.map((c) => (
          <li key={c.id}>
            <button type="button" onClick={() => onOpen(c.id)} className={cn("w-full flex items-center gap-2 px-2.5 h-9 text-sm text-left hover:bg-surface-2", isDone(project, c.status) && "opacity-70")}>
              <TypeIcon project={project} type={c.type} /><span className="num text-[11px] text-text-3">{c.key}</span>
              <span className={cn("flex-1 truncate", isDone(project, c.status) && "line-through")}>{c.title}</span>
              <PointsChip points={c.points} /><StatusBadge project={project} status={c.status} /><Avatar user={c.assignee} size={18} />
            </button>
          </li>
        ))}
        <li className="flex items-center gap-2 px-2.5 h-9 bg-surface-2/40">
          <Plus size={14} className="text-text-3" />
          {adding || children.length === 0 ? (
            <Input autoFocus={adding} value={title} onChange={(e) => setTitle(e.target.value)} placeholder={`Add a ${typeName} and press Enter (keeps going)`} className="h-7 text-xs bg-transparent border-none px-0" aria-label={`New ${typeName}`}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); submit(); } if (e.key === "Escape") { e.stopPropagation(); setAdding(false); setTitle(""); } }} onBlur={() => { if (!title) setAdding(false); }} />
          ) : <button type="button" onClick={() => setAdding(true)} className="text-xs text-text-3 hover:text-text">Add a {typeName}…</button>}
        </li>
      </ul>
    </section>
  );
}
