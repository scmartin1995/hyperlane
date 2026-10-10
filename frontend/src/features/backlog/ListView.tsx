// Flat list view with sortable columns.
import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import type { Project, Sprint, WorkItem } from "@/api/types";
import { ago, PRIORITY_ORDER } from "@/lib/format";
import { Avatar, Skeleton, cn } from "@/components/ui";
import { PointsChip, PriorityGlyph, StatusBadge, TypeIcon, isDone } from "@/features/items/common";

type Col = "key" | "type" | "title" | "status" | "priority" | "points" | "assignee" | "sprint" | "updated";
const COLS: { key: Col; label: string; cls?: string }[] = [
  { key: "key", label: "Key", cls: "w-20" }, { key: "type", label: "Type", cls: "w-12" }, { key: "title", label: "Title" }, { key: "status", label: "Status", cls: "w-32" },
  { key: "priority", label: "Prio", cls: "w-14" }, { key: "points", label: "Pts", cls: "w-12" }, { key: "assignee", label: "Who", cls: "w-14" }, { key: "sprint", label: "Sprint", cls: "w-28" }, { key: "updated", label: "Updated", cls: "w-24" },
];

export function ListView({ items, project, sprints, q, loading, selected, onSelect, onOpen }: {
  items: WorkItem[]; project: Project | undefined; sprints: Sprint[] | undefined; q: string; loading: boolean; selected: Set<string>; onSelect: (id: string, e: React.MouseEvent) => void; onOpen: (id: string) => void;
}) {
  const [sort, setSort] = useState<{ col: Col; dir: 1 | -1 }>({ col: "key", dir: 1 });
  const sprintName = (id: string | null) => sprints?.find((s) => s.id === id)?.name ?? "";
  const rows = useMemo(() => {
    const term = q.trim().toLowerCase();
    const list = items.filter((i) => !term || i.title.toLowerCase().includes(term) || i.key.toLowerCase().includes(term));
    const v = (i: WorkItem): string | number => {
      switch (sort.col) {
        case "key": return i.number; case "type": return i.type; case "title": return i.title.toLowerCase(); case "status": return project?.workflow.findIndex((s) => s.key === i.status) ?? 0;
        case "priority": return PRIORITY_ORDER.indexOf(i.priority); case "points": return i.points ?? -1; case "assignee": return i.assignee?.name ?? "~"; case "sprint": return sprintName(i.sprint_id) || "~"; case "updated": return i.updated_at;
      }
    };
    return list.sort((a, b) => { const x = v(a), y = v(b); return (x < y ? -1 : x > y ? 1 : 0) * sort.dir; });
  }, [items, q, sort, project, sprints]); // eslint-disable-line react-hooks/exhaustive-deps
  const toggleSort = (col: Col) => setSort((s) => (s.col === col ? { col, dir: s.dir === 1 ? -1 : 1 } : { col, dir: 1 }));
  if (loading) return <div className="space-y-2">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-9" />)}</div>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead><tr className="text-left">
          <th className="w-8 px-2" />
          {COLS.map((c) => <th key={c.key} className={cn("eyebrow font-semibold py-2 px-2 select-none cursor-pointer hover:text-text whitespace-nowrap", c.cls)} onClick={() => toggleSort(c.key)} aria-sort={sort.col === c.key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
            <span className="inline-flex items-center gap-1">{c.label}{sort.col === c.key && (sort.dir === 1 ? <ArrowUp size={10} /> : <ArrowDown size={10} />)}</span></th>)}
        </tr></thead>
        <tbody>
          {rows.map((i) => (
            <tr key={i.id} onClick={() => onOpen(i.id)} className={cn("border-t border-border hover:bg-surface-2 cursor-pointer", selected.has(i.id) && "bg-teal/10", isDone(project, i.status) && "opacity-70")}>
              <td className="px-2" onClick={(e) => e.stopPropagation()}><input type="checkbox" checked={selected.has(i.id)} onChange={() => undefined} onClick={(e) => onSelect(i.id, e)} aria-label={`Select ${i.key}`} className="accent-[var(--teal)]" /></td>
              <td className="px-2 py-1.5 num text-xs text-text-3">{i.key}</td>
              <td className="px-2"><TypeIcon project={project} type={i.type} /></td>
              <td className="px-2 py-1.5 max-w-[420px] truncate">{i.title}</td>
              <td className="px-2"><StatusBadge project={project} status={i.status} /></td>
              <td className="px-2"><PriorityGlyph priority={i.priority} /></td>
              <td className="px-2"><PointsChip points={i.points} /></td>
              <td className="px-2"><Avatar user={i.assignee} size={20} /></td>
              <td className="px-2 text-xs text-text-2 truncate">{sprintName(i.sprint_id) || <span className="text-text-3">—</span>}</td>
              <td className="px-2 text-[11px] text-text-3 whitespace-nowrap">{ago(i.updated_at)}</td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={10} className="py-8 text-center text-text-3 text-sm">Nothing matches.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
