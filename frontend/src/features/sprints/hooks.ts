import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { qk } from "@/api/queries";
import type { BurndownPoint, PlanSuggestion, Retro, Sprint, SprintCapacity, WorkItem } from "@/api/types";

export const useSprintItems = (id: string | undefined) => useQuery({ queryKey: ["items", "sprint", id] as const, queryFn: () => api.get<WorkItem[]>(`/sprints/${id}/items`), enabled: !!id });
export const useBurndown = (id: string | undefined) => useQuery({ queryKey: ["metrics", "burndown", id] as const, queryFn: () => api.get<BurndownPoint[]>(`/sprints/${id}/burndown`), enabled: !!id });
export const useSprintCapacity = (id: string | undefined) => useQuery({ queryKey: qk.sprintCapacity(id ?? ""), queryFn: () => api.get<SprintCapacity>(`/sprints/${id}/capacity`), enabled: !!id });
export const usePlanSuggest = (id: string | undefined, enabled = true) => useQuery({ queryKey: qk.planSuggest(id ?? ""), queryFn: () => api.get<PlanSuggestion>(`/sprints/${id}/plan/suggest`), enabled: !!id && enabled });
export const useRetro = (id: string | undefined) => useQuery({ queryKey: qk.retro(id ?? ""), queryFn: () => api.get<Retro>(`/sprints/${id}/retro`), enabled: !!id });

function useInvalidate() {
  const qc = useQueryClient();
  return (...keys: readonly (readonly unknown[])[]) => keys.forEach((k) => qc.invalidateQueries({ queryKey: k as unknown[] }));
}

export function useCreateSprint(pid: string | null) {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (b: { name?: string; goal?: string; start_date?: string; end_date?: string }) => api.post<Sprint>(`/projects/${pid}/sprints`, b), onSuccess: () => inv(["sprints"]) });
}
export function useUpdateSprint(id: string) {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (b: Partial<Pick<Sprint, "name" | "goal" | "start_date" | "end_date">>) => api.patch<Sprint>(`/sprints/${id}`, b), onSuccess: () => inv(["sprints"], qk.sprint(id)) });
}
export function useDeleteSprint() {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (id: string) => api.delete(`/sprints/${id}`), onSuccess: () => inv(["sprints"], ["items"]) });
}
export function useStartSprint(id: string) {
  const inv = useInvalidate();
  return useMutation({ mutationFn: () => api.post<Sprint>(`/sprints/${id}/start`), onSuccess: () => inv(["sprints"], qk.sprint(id), ["items"], ["project"]) });
}
export type CloseResult = { sprint: Sprint; carried: WorkItem[]; completed: WorkItem[] };
export function useCloseSprint(id: string) {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (carry_over: string) => api.post<CloseResult>(`/sprints/${id}/close`, { carry_over }), onSuccess: () => inv(["sprints"], qk.sprint(id), ["items"], ["metrics"], ["capacity"], ["project"]) });
}
export function usePutCapacity(id: string) {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (entries: { user_id: string; days_off: number; available_hours?: number; notes?: string }[]) => api.put<SprintCapacity>(`/sprints/${id}/capacity`, { entries }), onSuccess: () => inv(qk.sprintCapacity(id), qk.planSuggest(id)) });
}
export function useCommitPlan(id: string) {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (item_ids: string[]) => api.post<Sprint>(`/sprints/${id}/plan/commit`, { item_ids }), onSuccess: () => inv(["sprints"], qk.sprint(id), ["items"], qk.planSuggest(id), qk.sprintCapacity(id)) });
}
export function useRetroMutations(id: string) {
  const inv = useInvalidate();
  const done = () => inv(qk.retro(id));
  return {
    update: useMutation({ mutationFn: (b: Partial<Retro>) => api.put<Retro>(`/sprints/${id}/retro`, b), onSuccess: done }),
    addEntry: useMutation({ mutationFn: (b: { column: "went_well" | "improve" | "kudos" | "actions"; text: string; owner_id?: string | null }) => api.post<Retro>(`/sprints/${id}/retro/items`, b), onSuccess: done }),
    vote: useMutation({ mutationFn: (b: { column: string; entry_id: string }) => api.post<Retro>(`/sprints/${id}/retro/vote`, b), onSuccess: done }),
    mood: useMutation({ mutationFn: (score: number) => api.post<Retro>(`/sprints/${id}/retro/mood`, { score }), onSuccess: done }),
    generate: useMutation({ mutationFn: () => api.post<Retro>(`/sprints/${id}/retro/generate`), onSuccess: done }),
    close: useMutation({ mutationFn: () => api.post<Retro>(`/sprints/${id}/retro/close`), onSuccess: () => { done(); inv(["action-items"]); } }),
  };
}
