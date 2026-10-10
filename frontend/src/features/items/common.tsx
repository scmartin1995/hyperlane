// Small visual primitives shared by board/backlog/item detail: type icon, priority glyph, points chip, status badge…
import { Lock, CalendarClock } from "lucide-react";
import type { ItemType, Label, Priority, Project, WorkItem, WorkItemTreeNode } from "@/api/types";
import { categoryColor, fmtDate, overdue, priorityColor, priorityIcon, stateOf, typeOf } from "@/lib/format";
import { Badge, cn } from "@/components/ui";

export const PRIORITIES: Priority[] = ["critical", "high", "medium", "low", "none"];

export function TypeIcon({ project, type, size = "sm", className }: { project: Project | undefined; type: string; size?: "sm" | "md"; className?: string }) {
  const t = typeOf(project, type);
  const color = t?.color || "var(--smoke)";
  return (
    <span title={t?.name ?? type} aria-label={t?.name ?? type} className={cn("inline-flex items-center justify-center rounded-[5px] font-display font-bold shrink-0 leading-none", size === "sm" ? "w-5 h-5 text-[11px]" : "w-7 h-7 text-base", className)} style={{ background: `color-mix(in oklab, ${color} 18%, transparent)`, color }}>
      {t?.icon || type.slice(0, 1).toUpperCase()}
    </span>
  );
}
export function PriorityGlyph({ priority, withLabel }: { priority: Priority; withLabel?: boolean }) {
  if (priority === "none" && !withLabel) return null;
  return <span className="num text-[11px] font-bold inline-flex items-center gap-1" style={{ color: priorityColor(priority) }} title={`Priority: ${priority}`}>{priorityIcon[priority]}{withLabel && <span className="font-display capitalize">{priority}</span>}</span>;
}
export function PointsChip({ points, className }: { points: number | null | undefined; className?: string }) {
  if (points == null) return null;
  return <span className={cn("num inline-flex items-center justify-center h-[18px] min-w-[18px] px-1.5 rounded-full bg-surface-3 border border-border text-[10px] font-semibold text-text-2", className)} title={`${points} points`}>{points}</span>;
}
export function StatusBadge({ project, status, size = "xs" }: { project: Project | undefined; status: string; size?: "xs" | "sm" }) {
  const s = stateOf(project, status);
  return <Badge color={s?.color || categoryColor(s?.category ?? "todo")} dot size={size}>{s?.name ?? status}</Badge>;
}
export function DueChip({ due, done }: { due: string | null; done?: boolean }) {
  if (!due) return null;
  const late = !done && overdue(due);
  return <span className={cn("inline-flex items-center gap-1 text-[10px] num", late ? "text-rust-light font-semibold" : "text-text-3")} title={late ? "Overdue" : "Due date"}><CalendarClock size={11} />{fmtDate(due)}</span>;
}
export function LabelChips({ labels, max = 3 }: { labels: Label[]; max?: number }) {
  if (!labels?.length) return null;
  const shown = labels.slice(0, max);
  return <span className="inline-flex flex-wrap gap-1">{shown.map((l) => <Badge key={l.id} size="xs" color={l.color || undefined}>{l.name}</Badge>)}{labels.length > max && <Badge size="xs">+{labels.length - max}</Badge>}</span>;
}
export function BlockedTag({ reason }: { reason?: string | null }) {
  return <span className="inline-flex items-center gap-1 text-[10px] font-display font-semibold text-rust-light" title={reason ?? "Blocked"}><Lock size={11} />Blocked</span>;
}

/* ---------- helpers ---------- */
export const isDone = (project: Project | undefined, status: string) => stateOf(project, status)?.category === "done";
export const isInProgress = (project: Project | undefined, status: string) => stateOf(project, status)?.category === "in_progress";
export const typesByLevel = (project: Project | undefined): ItemType[] => [...(project?.item_types ?? [])].sort((a, b) => a.level - b.level);
/** The natural child type of a given type (next level down), falling back to the project default. */
export function childTypeOf(project: Project | undefined, type: string | undefined): string {
  const types = typesByLevel(project);
  const t = types.find((x) => x.key === type);
  const next = t ? types.find((x) => x.level > t.level) : undefined;
  return next?.key ?? project?.settings.default_type ?? types[types.length - 1]?.key ?? "story";
}
export function descendantIds(node: WorkItemTreeNode): string[] {
  const out: string[] = [];
  const walk = (n: WorkItemTreeNode) => n.children?.forEach((c) => { out.push(c.id); walk(c); });
  walk(node);
  return out;
}
export function findNode(tree: WorkItemTreeNode[], id: string): WorkItemTreeNode | undefined {
  for (const n of tree) { if (n.id === id) return n; const f = findNode(n.children ?? [], id); if (f) return f; }
  return undefined;
}
/** Walk parent_id links to the top-level ancestor. */
export function rootOf(item: WorkItem, byId: Map<string, WorkItem>): WorkItem {
  let cur = item; let guard = 0;
  while (cur.parent_id && byId.has(cur.parent_id) && guard++ < 50) cur = byId.get(cur.parent_id)!;
  return cur;
}
export const sumPoints = (items: WorkItem[]) => items.reduce((a, i) => a + (i.points ?? 0), 0);
