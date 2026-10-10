import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { qk } from "@/api/queries";
import type { IntakeRequest, WorkItem } from "@/api/types";

export const useIntakeList = (state?: string) => useQuery({ queryKey: [...qk.intake, "list", state ?? "all"] as const, queryFn: () => api.get<IntakeRequest[]>(`/intake${state ? `?state=${state}` : ""}`) });
export const useIntakeOne = (id: string | undefined) => useQuery({ queryKey: qk.intakeOne(id ?? ""), queryFn: () => api.get<IntakeRequest>(`/intake/${id}`), enabled: !!id });

export function useIntakeMutations(id?: string) {
  const qc = useQueryClient();
  const inv = () => qc.invalidateQueries({ queryKey: qk.intake });
  return {
    create: useMutation({ mutationFn: (b: { subject: string; body: string; requester_name?: string; requester_email?: string; project_id?: string | null; channel?: string }) => api.post<IntakeRequest>("/intake", b), onSuccess: inv }),
    message: useMutation({ mutationFn: (b: { body: string; direction?: "inbound" | "internal"; author?: string }) => api.post<IntakeRequest>(`/intake/${id}/messages`, b), onSuccess: inv }),
    analyze: useMutation({ mutationFn: () => api.post<IntakeRequest>(`/intake/${id}/analyze`), onSuccess: inv }),
    convert: useMutation({ mutationFn: (b: { project_id: string; parent_id?: string | null; items?: { type: string; title: string; description?: string; points?: number | null; acceptance_criteria?: string }[] }) => api.post<WorkItem[]>(`/intake/${id}/convert`, b), onSuccess: () => { inv(); qc.invalidateQueries({ queryKey: ["items"] }); } }),
    reject: useMutation({ mutationFn: (reason?: string) => api.post<IntakeRequest>(`/intake/${id}/reject`, { reason }), onSuccess: inv }),
    patch: useMutation({ mutationFn: (b: { owner_id?: string | null; project_id?: string | null; state?: IntakeRequest["state"]; max_questions?: number }) => api.patch<IntakeRequest>(`/intake/${id}`, b), onSuccess: inv }),
  };
}
