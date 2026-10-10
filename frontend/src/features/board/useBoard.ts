// Pure board logic: filters, swimlanes, container ids. Kept free of React so it's easy to reason about.
import type { Project, User, WorkItem, WorkItemInput } from "@/api/types";
import { rootOf } from "@/features/items/common";

export type LaneMode = "none" | "epic" | "assignee";
export interface BoardFilters { q: string; assignees: string[]; type: string; label: string; mine: boolean; activeOnly: boolean | null; lane: LaneMode }
export const DEFAULT_FILTERS: BoardFilters = { q: "", assignees: [], type: "", label: "", mine: false, activeOnly: null, lane: "none" };
export const hasActiveFilters = (f: BoardFilters) => !!(f.q || f.assignees.length || f.type || f.label || f.mine);

export function filterItems(items: WorkItem[], f: BoardFilters, meId: string | undefined, activeSprintId: string | undefined): WorkItem[] {
  const q = f.q.trim().toLowerCase();
  const activeOnly = f.activeOnly ?? !!activeSprintId;
  return items.filter((i) => {
    if (i.is_archived) return false;
    if (activeOnly && activeSprintId && i.sprint_id !== activeSprintId) return false;
    if (f.type && i.type !== f.type) return false;
    if (f.label && !i.labels.some((l) => l.name === f.label)) return false;
    if (f.mine && i.assignee_id !== meId) return false;
    if (f.assignees.length && !f.assignees.includes(i.assignee_id ?? "none")) return false;
    if (q && !(i.title.toLowerCase().includes(q) || i.key.toLowerCase().includes(q))) return false;
    return true;
  });
}

export interface Lane { key: string; title: string; subtitle?: string; color?: string; items: WorkItem[]; defaults: Partial<WorkItemInput> }
export function buildLanes(filtered: WorkItem[], all: WorkItem[], mode: LaneMode, users: User[] | undefined, project: Project | undefined): Lane[] {
  if (mode === "none") return [{ key: "all", title: "All", items: filtered, defaults: {} }];
  const lanes = new Map<string, Lane>();
  if (mode === "assignee") {
    for (const i of filtered) {
      const k = i.assignee_id ?? "none";
      if (!lanes.has(k)) { const u = users?.find((x) => x.id === k); lanes.set(k, { key: k, title: u ? `${u.emoji} ${u.name}` : "Unassigned", subtitle: u?.role, color: u?.color, items: [], defaults: { assignee_id: u ? u.id : null } }); }
      lanes.get(k)!.items.push(i);
    }
    return [...lanes.values()].sort((a, b) => (a.key === "none" ? 1 : b.key === "none" ? -1 : a.title.localeCompare(b.title)));
  }
  const byId = new Map(all.map((i) => [i.id, i]));
  for (const i of filtered) {
    const root = rootOf(i, byId);
    const k = root.id === i.id && !i.parent_id ? (i.child_count > 0 || isTopType(project, i.type) ? i.id : "none") : root.id;
    if (!lanes.has(k)) { const r = byId.get(k); lanes.set(k, r ? { key: k, title: r.title, subtitle: r.key, color: project?.item_types.find((t) => t.key === r.type)?.color, items: [], defaults: { parent_id: r.id } } : { key: "none", title: "No epic", subtitle: "Top-level items", items: [], defaults: {} }); }
    lanes.get(k)!.items.push(i);
  }
  return [...lanes.values()].sort((a, b) => (a.key === "none" ? 1 : b.key === "none" ? -1 : 0));
}
const isTopType = (project: Project | undefined, type: string) => { const t = project?.item_types.find((x) => x.key === type); return !!t && t.level === Math.min(...(project?.item_types.map((x) => x.level) ?? [0])); };

export const cid = (lane: string, status: string) => `${lane}::${status}`;
export const parseCid = (id: string) => { const i = id.lastIndexOf("::"); return { lane: id.slice(0, i), status: id.slice(i + 2) }; };
export function buildContainers(lanes: Lane[], project: Project | undefined): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const lane of lanes) for (const s of project?.workflow ?? []) out[cid(lane.key, s.key)] = lane.items.filter((i) => i.status === s.key).map((i) => i.id);
  return out;
}
export function findContainer(containers: Record<string, string[]>, id: string): string | undefined {
  if (containers[id]) return id;
  return Object.keys(containers).find((k) => containers[k].includes(id));
}
