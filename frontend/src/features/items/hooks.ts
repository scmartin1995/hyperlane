// Shared work-item hooks (frontend-a). Other features may import these.
// Every mutation is optimistic where it is safe and invalidates qk.items / qk.itemTree / qk.item on settle.
import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { qk } from "@/api/queries";
import type {
  Activity, Comment, Label, MoveInput, MoveResult, Sprint, StatusTransition, User, WorkItem, WorkItemDetail, WorkItemInput, WorkItemTreeNode,
} from "@/api/types";
import { toast } from "@/components/ui";

export interface ItemsParams {
  type?: string; status?: string; category?: string; sprint_id?: string; assignee_id?: string; parent_id?: string; q?: string; label?: string;
  unscheduled?: boolean; include_archived?: boolean; include_done?: boolean; limit?: number;
}
export function qs(params?: Record<string, unknown>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  const s = sp.toString();
  return s ? `?${s}` : "";
}

/* ---------- reads ---------- */
export const useItems = (pid: string | undefined, params?: ItemsParams) =>
  useQuery({ queryKey: qk.items(pid ?? "", params as Record<string, unknown>), queryFn: () => api.get<WorkItem[]>(`/projects/${pid}/items${qs(params as Record<string, unknown>)}`), enabled: !!pid });
export const useItemTree = (pid: string | undefined, includeDone = true) =>
  useQuery({ queryKey: [...qk.itemTree(pid ?? ""), { includeDone }] as const, queryFn: () => api.get<WorkItemTreeNode[]>(`/projects/${pid}/items/tree?include_done=${includeDone}`), enabled: !!pid });
export const useItem = (id: string | undefined | null) =>
  useQuery({ queryKey: qk.item(id ?? ""), queryFn: () => api.get<WorkItemDetail>(`/items/${id}`), enabled: !!id });
export const useItemActivity = (id: string | undefined | null) =>
  useQuery({ queryKey: [...qk.item(id ?? ""), "activity"] as const, queryFn: () => api.get<Activity[]>(`/items/${id}/activity`), enabled: !!id });
export const useItemTransitions = (id: string | undefined | null) =>
  useQuery({ queryKey: [...qk.item(id ?? ""), "transitions"] as const, queryFn: () => api.get<StatusTransition[]>(`/items/${id}/transitions`), enabled: !!id });
export const useSprints = (pid: string | undefined, state?: Sprint["state"]) =>
  useQuery({ queryKey: state ? ([...qk.sprints(pid ?? ""), state] as const) : qk.sprints(pid ?? ""), queryFn: () => api.get<Sprint[]>(`/projects/${pid}/sprints${qs({ state })}`), enabled: !!pid });
export const useLabels = (pid: string | undefined) =>
  useQuery({ queryKey: qk.labels(pid ?? ""), queryFn: () => api.get<Label[]>(`/projects/${pid}/labels`), enabled: !!pid });

/* ---------- cache helpers ---------- */
type AnyNode = WorkItem & { children?: WorkItemTreeNode[] };
function mapNodes<T extends AnyNode>(list: T[], id: string, patch: Partial<WorkItem>): T[] {
  return list.map((n) => {
    const next = n.id === id ? { ...n, ...patch } : n;
    if (Array.isArray(next.children) && next.children.length) return { ...next, children: mapNodes(next.children, id, patch) };
    return next;
  });
}
/** Reorder a flat list to reflect a move (status/sprint/parent patch + before/after placement). */
export function applyMoveToList(list: WorkItem[], id: string, move: MoveInput, extra: Partial<WorkItem> = {}): WorkItem[] {
  const item = list.find((i) => i.id === id);
  if (!item) return list;
  const patched: WorkItem = { ...item, ...extra };
  if (move.status !== undefined) patched.status = move.status;
  if (move.sprint_id !== undefined) patched.sprint_id = move.sprint_id;
  if (move.parent_id !== undefined) patched.parent_id = move.parent_id;
  const rest = list.filter((i) => i.id !== id);
  if (move.before_id) { const idx = rest.findIndex((i) => i.id === move.before_id); if (idx >= 0) { rest.splice(idx, 0, patched); return rest; } }
  if (move.after_id) { const idx = rest.findIndex((i) => i.id === move.after_id); if (idx >= 0) { rest.splice(idx + 1, 0, patched); return rest; } }
  if (move.before_id === undefined && move.after_id === undefined) { const idx = list.findIndex((i) => i.id === id); rest.splice(idx, 0, patched); return rest; }
  rest.push(patched);
  return rest;
}
export function patchItemEverywhere(qc: QueryClient, id: string, patch: Partial<WorkItem>) {
  qc.setQueriesData<AnyNode[]>({ queryKey: ["items"] }, (old) => (Array.isArray(old) ? mapNodes(old, id, patch) : old));
  qc.setQueryData<WorkItemDetail>(qk.item(id), (old) => (old ? { ...old, ...patch } : old));
}
function invalidateItems(qc: QueryClient, id?: string) {
  qc.invalidateQueries({ queryKey: ["items"] });
  if (id) qc.invalidateQueries({ queryKey: qk.item(id) });
  qc.invalidateQueries({ queryKey: ["project"] });
  qc.invalidateQueries({ queryKey: ["metrics"] });
  qc.invalidateQueries({ queryKey: ["activity"] });
}
/** Turn a WorkItemInput patch into the optimistic WorkItem fields we can predict client-side. */
function optimisticFields(qc: QueryClient, patch: Partial<WorkItemInput>): Partial<WorkItem> {
  const { labels: _labels, ...rest } = patch;
  const out: Partial<WorkItem> = { ...(rest as Partial<WorkItem>) };
  if ("assignee_id" in patch) {
    const users = qc.getQueryData<User[]>(qk.users);
    out.assignee = users?.find((u) => u.id === patch.assignee_id) ?? null;
  }
  return out;
}
const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e));

/* ---------- mutations ---------- */
export function useCreateItem(pid: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: WorkItemInput) => api.post<WorkItem>(`/projects/${pid}/items`, input),
    onSuccess: (item) => { invalidateItems(qc); if (item.parent_id) qc.invalidateQueries({ queryKey: qk.item(item.parent_id) }); },
    onError: (e) => toast.error("Couldn't create the item", errMsg(e)),
  });
}

export function useUpdateItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<WorkItemInput> }) => api.patch<WorkItem>(`/items/${id}`, patch),
    onMutate: async ({ id, patch }) => {
      await qc.cancelQueries({ queryKey: qk.item(id) });
      const prev = qc.getQueryData<WorkItemDetail>(qk.item(id));
      patchItemEverywhere(qc, id, optimisticFields(qc, patch));
      return { prev };
    },
    onError: (e, { id }, ctx) => { if (ctx?.prev) qc.setQueryData(qk.item(id), ctx.prev); toast.error("Couldn't save", errMsg(e)); },
    onSettled: (_d, _e, { id }) => invalidateItems(qc, id),
  });
}

export function useMoveItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, move }: { id: string; move: MoveInput }) => api.post<MoveResult>(`/items/${id}/move`, move),
    onMutate: async ({ id, move }) => {
      await qc.cancelQueries({ queryKey: ["items"] });
      qc.setQueriesData<AnyNode[]>({ queryKey: ["items"] }, (old) => {
        if (!Array.isArray(old)) return old;
        const isTree = old.some((n) => Array.isArray(n.children));
        if (isTree) { const p: Partial<WorkItem> = {}; if (move.status !== undefined) p.status = move.status; if (move.sprint_id !== undefined) p.sprint_id = move.sprint_id; return mapNodes(old, id, p); }
        return applyMoveToList(old as WorkItem[], id, move);
      });
      const p: Partial<WorkItem> = {};
      if (move.status !== undefined) p.status = move.status; if (move.sprint_id !== undefined) p.sprint_id = move.sprint_id; if (move.parent_id !== undefined) p.parent_id = move.parent_id;
      qc.setQueryData<WorkItemDetail>(qk.item(id), (old) => (old ? { ...old, ...p } : old));
    },
    onSuccess: (res) => { if (res?.wip_warning) toast.info("WIP limit", res.wip_warning); },
    onError: (e) => { toast.error("Couldn't move the item", errMsg(e)); invalidateItems(qc); },
    onSettled: (_d, _e, { id }) => invalidateItems(qc, id),
  });
}

export function useBulkUpdate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ ids, patch }: { ids: string[]; patch: Partial<WorkItemInput> }) => api.post<WorkItem[]>(`/items/bulk-update`, { ids, patch }),
    onMutate: ({ ids, patch }) => { const f = optimisticFields(qc, patch); ids.forEach((id) => patchItemEverywhere(qc, id, f)); },
    onError: (e) => toast.error("Bulk update failed", errMsg(e)),
    onSettled: () => invalidateItems(qc),
  });
}

export function useDeleteItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, hard }: { id: string; hard?: boolean }) => api.delete<void>(`/items/${id}${hard ? "?hard=true" : ""}`),
    onError: (e) => toast.error("Couldn't archive the item", errMsg(e)),
    onSettled: () => invalidateItems(qc),
  });
}

export function useAddComment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ item_id, body, is_decision }: { item_id: string; body: string; is_decision?: boolean }) => api.post<Comment>(`/items/${item_id}/comments`, { body, is_decision: !!is_decision }),
    onMutate: async ({ item_id, body, is_decision }) => {
      await qc.cancelQueries({ queryKey: qk.item(item_id) });
      const me = qc.getQueryData<User | null>(qk.me);
      const temp: Comment = { id: `tmp-${Date.now()}`, work_item_id: item_id, author_id: me?.id ?? null, author_name: me?.name ?? null, author: me ?? null, body, source: "web", external_ref: null, is_decision: !!is_decision, created_at: new Date().toISOString(), edited_at: null };
      qc.setQueryData<WorkItemDetail>(qk.item(item_id), (old) => (old ? { ...old, comments: [...old.comments, temp], comment_count: old.comment_count + 1 } : old));
    },
    onError: (e) => toast.error("Couldn't post the comment", errMsg(e)),
    onSettled: (_d, _e, { item_id }) => { qc.invalidateQueries({ queryKey: qk.item(item_id) }); qc.invalidateQueries({ queryKey: ["items"] }); },
  });
}
export function useUpdateComment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; item_id: string; patch: { body?: string; is_decision?: boolean } }) => api.patch<Comment>(`/comments/${id}`, patch),
    onMutate: ({ id, item_id, patch }) => qc.setQueryData<WorkItemDetail>(qk.item(item_id), (old) => (old ? { ...old, comments: old.comments.map((c) => (c.id === id ? { ...c, ...patch } : c)) } : old)),
    onError: (e) => toast.error("Couldn't update the comment", errMsg(e)),
    onSettled: (_d, _e, { item_id }) => qc.invalidateQueries({ queryKey: qk.item(item_id) }),
  });
}
export function useDeleteComment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: string; item_id: string }) => api.delete<void>(`/comments/${id}`),
    onMutate: ({ id, item_id }) => qc.setQueryData<WorkItemDetail>(qk.item(item_id), (old) => (old ? { ...old, comments: old.comments.filter((c) => c.id !== id) } : old)),
    onError: (e) => toast.error("Couldn't delete the comment", errMsg(e)),
    onSettled: (_d, _e, { item_id }) => qc.invalidateQueries({ queryKey: qk.item(item_id) }),
  });
}

/* ---------- keyboard ---------- */
export function isTypingTarget(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || !!el.isContentEditable;
}
/** Global single-key shortcut (ignored while typing unless allowInInput). `ctrl` matches Ctrl or Cmd. */
export function useHotkey(key: string, handler: (e: KeyboardEvent) => void, opts: { ctrl?: boolean; enabled?: boolean; allowInInput?: boolean } = {}) {
  const ref = useRef(handler);
  ref.current = handler;
  const { ctrl = false, enabled = true, allowInInput = false } = opts;
  useEffect(() => {
    if (!enabled) return;
    const k = (e: KeyboardEvent) => {
      if (!allowInInput && isTypingTarget(e.target)) return;
      if (ctrl !== (e.ctrlKey || e.metaKey)) return;
      if (e.altKey) return;
      if (e.key.toLowerCase() !== key.toLowerCase()) return;
      ref.current(e);
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [key, ctrl, enabled, allowInInput]);
}
