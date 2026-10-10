import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { qk } from "@/api/queries";
import type { ImportPreview, ItemType, Label, NotificationLogEntry, Project, Workspace, WorkflowState, WorkItem } from "@/api/types";

export type ProjectPatch = Partial<Pick<Project, "name" | "key" | "description" | "color" | "icon" | "lead_id" | "settings" | "slack_channel" | "status">> & { workflow?: WorkflowState[]; item_types?: ItemType[]; workflow_rename?: Record<string, string> };

export function useUpdateWorkspace() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (b: Partial<Workspace>) => api.patch<Workspace>("/workspace", b), onSuccess: () => qc.invalidateQueries({ queryKey: qk.workspace }) });
}
export function useUpdateProject(id: string) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (b: ProjectPatch) => api.patch<Project>(`/projects/${id}`, b), onSuccess: () => { qc.invalidateQueries({ queryKey: qk.projects }); qc.invalidateQueries({ queryKey: qk.project(id) }); qc.invalidateQueries({ queryKey: ["items"] }); } });
}
export function useArchiveProject() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (id: string) => api.delete(`/projects/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: qk.projects }) });
}
export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (b: { name: string; key?: string; template: string; description?: string; color?: string; icon?: string; lead_id?: string | null }) => api.post<Project>("/projects", b), onSuccess: () => qc.invalidateQueries({ queryKey: qk.projects }) });
}
export const useLabels = (pid: string) => useQuery({ queryKey: qk.labels(pid), queryFn: () => api.get<Label[]>(`/projects/${pid}/labels`) });
export function useLabelMutations(pid: string) {
  const qc = useQueryClient(); const inv = () => qc.invalidateQueries({ queryKey: qk.labels(pid) });
  return {
    create: useMutation({ mutationFn: (b: { name: string; color?: string }) => api.post<Label>(`/projects/${pid}/labels`, b), onSuccess: inv }),
    update: useMutation({ mutationFn: ({ id, ...b }: { id: string; name?: string; color?: string }) => api.patch<Label>(`/labels/${id}`, b), onSuccess: inv }),
    remove: useMutation({ mutationFn: (id: string) => api.delete(`/labels/${id}`), onSuccess: inv }),
  };
}
export const useNotificationLog = () => useQuery({ queryKey: ["notifications-log"], queryFn: () => api.get<NotificationLogEntry[]>("/notifications/log?limit=50") });
export const useTestIntegration = () => useMutation({ mutationFn: (kind: "slack" | "teams" | "email") => api.post<{ ok: boolean; detail: string }>(`/integrations/test/${kind}`) });
export const useImportPreview = (pid: string) => useMutation({ mutationFn: (form: FormData) => api.upload<ImportPreview>(`/projects/${pid}/import/excel/preview`, form) });
export function useImportCommit(pid: string) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (b: { file_token: string; sheet: string; mapping: Record<string, string | null>; create_missing_users?: boolean }) => api.post<{ created: WorkItem[]; skipped: number; warnings: string[] }>(`/projects/${pid}/import/excel/commit`, b), onSuccess: () => { qc.invalidateQueries({ queryKey: ["items"] }); qc.invalidateQueries({ queryKey: qk.users }); } });
}
