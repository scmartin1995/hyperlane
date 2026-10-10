// Pure tree helpers for the backlog: rollups, flattening with collapse/search, local reorder/re-parent.
import type { Project, WorkItemTreeNode } from "@/api/types";
import { isDone } from "@/features/items/common";

export interface Rollup { total: number; done: number; points: number; donePoints: number }
export interface Row { node: WorkItemTreeNode; depth: number; parentId: string | null; rollup: Rollup; hasChildren: boolean }

export function computeRollups(tree: WorkItemTreeNode[], project: Project | undefined): Map<string, Rollup> {
  const map = new Map<string, Rollup>();
  const walk = (n: WorkItemTreeNode): Rollup => {
    const r: Rollup = { total: 0, done: 0, points: 0, donePoints: 0 };
    for (const c of n.children ?? []) {
      const cr = walk(c); const d = isDone(project, c.status);
      r.total += 1 + cr.total; r.done += (d ? 1 : 0) + cr.done;
      r.points += (c.points ?? 0) + cr.points; r.donePoints += (d ? c.points ?? 0 : 0) + cr.donePoints;
    }
    map.set(n.id, r);
    return r;
  };
  tree.forEach(walk);
  return map;
}

/** Visible rows. With a search term, only matching nodes + their ancestors are shown and everything is expanded. */
export function flatten(tree: WorkItemTreeNode[], collapsed: Set<string>, rollups: Map<string, Rollup>, q: string, hideDone: boolean, project: Project | undefined): Row[] {
  const term = q.trim().toLowerCase();
  const matches = (n: WorkItemTreeNode) => !term || n.title.toLowerCase().includes(term) || n.key.toLowerCase().includes(term);
  const keep = (n: WorkItemTreeNode): boolean => {
    if (hideDone && isDone(project, n.status) && !(n.children ?? []).some(keep)) return false;
    return matches(n) || (n.children ?? []).some(keep);
  };
  const out: Row[] = [];
  const walk = (list: WorkItemTreeNode[], depth: number, parentId: string | null) => {
    for (const n of list) {
      if (!keep(n)) continue;
      const kids = n.children ?? [];
      out.push({ node: n, depth, parentId, rollup: rollups.get(n.id) ?? { total: 0, done: 0, points: 0, donePoints: 0 }, hasChildren: kids.length > 0 });
      if (kids.length && (term || !collapsed.has(n.id))) walk(kids, depth + 1, n.id);
    }
  };
  walk(tree, 0, null);
  return out;
}

export function removeNode(tree: WorkItemTreeNode[], id: string): { tree: WorkItemTreeNode[]; node: WorkItemTreeNode | null } {
  let found: WorkItemTreeNode | null = null;
  const walk = (list: WorkItemTreeNode[]): WorkItemTreeNode[] => list.flatMap((n) => {
    if (n.id === id) { found = n; return []; }
    return [{ ...n, children: walk(n.children ?? []) }];
  });
  const next = walk(tree);
  return { tree: next, node: found };
}
/** Move `id` under `parentId` (null = root), placed before/after a sibling or last. */
export function moveNode(tree: WorkItemTreeNode[], id: string, to: { parentId: string | null; beforeId?: string; afterId?: string }): WorkItemTreeNode[] {
  const { tree: without, node } = removeNode(tree, id);
  if (!node) return tree;
  const moved: WorkItemTreeNode = { ...node, parent_id: to.parentId };
  const insert = (list: WorkItemTreeNode[]): WorkItemTreeNode[] => {
    const next = [...list];
    const bi = to.beforeId ? next.findIndex((n) => n.id === to.beforeId) : -1;
    const ai = to.afterId ? next.findIndex((n) => n.id === to.afterId) : -1;
    if (bi >= 0) next.splice(bi, 0, moved); else if (ai >= 0) next.splice(ai + 1, 0, moved); else next.push(moved);
    return next;
  };
  if (to.parentId === null) return insert(without);
  const walk = (list: WorkItemTreeNode[]): WorkItemTreeNode[] => list.map((n) => (n.id === to.parentId ? { ...n, children: insert(n.children ?? []), child_count: (n.children?.length ?? 0) + 1 } : { ...n, children: walk(n.children ?? []) }));
  return walk(without);
}
/** Index in `rows` after which a new child of `parentId` should render (after its last visible descendant). */
export function insertionIndex(rows: Row[], parentId: string | null): number {
  if (parentId === null) return rows.length;
  const pi = rows.findIndex((r) => r.node.id === parentId);
  if (pi < 0) return rows.length;
  const depth = rows[pi].depth;
  let i = pi + 1;
  while (i < rows.length && rows[i].depth > depth) i++;
  return i;
}
