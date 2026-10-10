import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { qk } from "@/api/queries";
import type { ActionItem, Priority } from "@/api/types";

export type ActionInput = { title?: string; notes?: string | null; due_date?: string | null; priority?: Priority; tags?: string[]; work_item_id?: string | null; project_id?: string | null; source?: string; done?: boolean; snoozed_until?: string | null };
const KEY = qk.actionItems;

export function useActionMutations() {
  const qc = useQueryClient();
  const inv = () => qc.invalidateQueries({ queryKey: KEY });
  const patchCache = (id: string, patch: Partial<ActionItem>) => qc.setQueriesData<ActionItem[]>({ queryKey: KEY }, (old) => old?.map((a) => (a.id === id ? { ...a, ...patch } : a)));
  return {
    create: useMutation({ mutationFn: (b: ActionInput & { title: string }) => api.post<ActionItem>("/me/action-items", b), onSuccess: inv }),
    update: useMutation({
      mutationFn: ({ id, ...b }: ActionInput & { id: string }) => api.patch<ActionItem>(`/me/action-items/${id}`, b),
      onMutate: async ({ id, ...b }) => { await qc.cancelQueries({ queryKey: KEY }); const prev = qc.getQueriesData<ActionItem[]>({ queryKey: KEY }); patchCache(id, b as Partial<ActionItem>); return { prev }; },
      onError: (_e, _v, ctx) => ctx?.prev.forEach(([k, d]) => qc.setQueryData(k, d)),
      onSettled: inv,
    }),
    remove: useMutation({ mutationFn: (id: string) => api.delete(`/me/action-items/${id}`), onSuccess: inv }),
    reorder: useMutation({
      mutationFn: (ids: string[]) => api.post("/me/action-items/reorder", { ids }),
      onMutate: async (ids) => { await qc.cancelQueries({ queryKey: KEY }); const prev = qc.getQueriesData<ActionItem[]>({ queryKey: KEY }); qc.setQueriesData<ActionItem[]>({ queryKey: KEY }, (old) => old ? [...old].sort((a, b) => { const ia = ids.indexOf(a.id), ib = ids.indexOf(b.id); return (ia < 0 ? 1e9 : ia) - (ib < 0 ? 1e9 : ib); }) : old); return { prev }; },
      onError: (_e, _v, ctx) => ctx?.prev.forEach(([k, d]) => qc.setQueryData(k, d)),
      onSettled: inv,
    }),
  };
}
