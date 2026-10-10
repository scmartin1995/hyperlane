import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { qk } from "@/api/queries";
import type { CapacityProfile, User, WorkItem } from "@/api/types";

export type UserInput = Partial<Pick<User, "name" | "handle" | "email" | "role" | "emoji" | "color" | "skills" | "hours_per_week" | "focus_factor" | "timezone" | "slack_user_id" | "bio" | "preferences" | "is_active">>;
export const useUser = (id: string | undefined) => useQuery({ queryKey: [...qk.users, id] as const, queryFn: () => api.get<User>(`/users/${id}`), enabled: !!id });
export const useProjectCapacity = (pid: string | null) => useQuery({ queryKey: qk.capacity(pid ?? ""), queryFn: () => api.get<CapacityProfile[]>(`/projects/${pid}/capacity`), enabled: !!pid });
export const useUserItems = (pid: string | null, uid: string | undefined) => useQuery({ queryKey: qk.items(pid ?? "", { assignee_id: uid, include_done: false }), queryFn: () => api.get<WorkItem[]>(`/projects/${pid}/items?assignee_id=${uid}&include_done=false`), enabled: !!pid && !!uid });

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (b: UserInput & { name: string }) => api.post<User>("/users", b), onSuccess: () => { qc.invalidateQueries({ queryKey: qk.users }); qc.invalidateQueries({ queryKey: qk.profiles }); } });
}
export function useUpdateUser(id: string) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (b: UserInput) => api.patch<User>(`/users/${id}`, b), onSuccess: () => { qc.invalidateQueries({ queryKey: qk.users }); qc.invalidateQueries({ queryKey: qk.profiles }); qc.invalidateQueries({ queryKey: qk.me }); } });
}
export function useSetPin() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (pin: string | null) => api.post("/auth/pin", { pin }), onSuccess: () => { qc.invalidateQueries({ queryKey: qk.me }); qc.invalidateQueries({ queryKey: qk.users }); } });
}
