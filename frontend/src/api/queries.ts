// Query keys + the handful of hooks every feature needs. Features add their own hooks in their folder.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { Health, Project, ProjectSummary, Template, User, UserBrief, Workspace } from "./types";

export const qk = {
  health: ["health"] as const,
  me: ["me"] as const,
  profiles: ["profiles"] as const,
  users: ["users"] as const,
  workspace: ["workspace"] as const,
  templates: ["templates"] as const,
  projects: ["projects"] as const,
  project: (id: string) => ["project", id] as const,
  projectSummary: (id: string) => ["project", id, "summary"] as const,
  items: (pid: string, params?: Record<string, unknown>) => ["items", pid, params ?? {}] as const,
  itemTree: (pid: string) => ["items", pid, "tree"] as const,
  item: (id: string) => ["item", id] as const,
  sprints: (pid: string) => ["sprints", pid] as const,
  sprint: (id: string) => ["sprint", id] as const,
  labels: (pid: string) => ["labels", pid] as const,
  activity: (pid: string) => ["activity", pid] as const,
  actionItems: ["action-items"] as const,
  metrics: (pid: string, name: string, params?: Record<string, unknown>) => ["metrics", pid, name, params ?? {}] as const,
  evm: (pid: string) => ["evm", pid] as const,
  capacity: (pid: string) => ["capacity", pid] as const,
  sprintCapacity: (sid: string) => ["sprint-capacity", sid] as const,
  planSuggest: (sid: string) => ["plan-suggest", sid] as const,
  retro: (sid: string) => ["retro", sid] as const,
  intake: ["intake"] as const,
  intakeOne: (id: string) => ["intake", id] as const,
  chatThreads: ["chat-threads"] as const,
  chatThread: (id: string) => ["chat-thread", id] as const,
  integrations: ["integrations"] as const,
  agentStatus: ["agent-status"] as const,
};

export const useHealth = () => useQuery({ queryKey: qk.health, queryFn: () => api.get<Health>("/health") });
export const useMe = () => useQuery({ queryKey: qk.me, queryFn: () => api.get<User | null>("/auth/me") });
export const useProfiles = () => useQuery({ queryKey: qk.profiles, queryFn: () => api.get<UserBrief[]>("/auth/profiles") });
export const useUsers = () => useQuery({ queryKey: qk.users, queryFn: () => api.get<User[]>("/users") });
export const useWorkspace = () => useQuery({ queryKey: qk.workspace, queryFn: () => api.get<Workspace>("/workspace") });
export const useTemplates = () => useQuery({ queryKey: qk.templates, queryFn: () => api.get<Template[]>("/templates"), staleTime: Infinity });
export const useProjects = () => useQuery({ queryKey: qk.projects, queryFn: () => api.get<Project[]>("/projects") });
export const useProject = (id: string | undefined) => useQuery({ queryKey: qk.project(id ?? ""), queryFn: () => api.get<Project>(`/projects/${id}`), enabled: !!id });
export const useProjectSummary = (id: string | undefined) => useQuery({ queryKey: qk.projectSummary(id ?? ""), queryFn: () => api.get<ProjectSummary>(`/projects/${id}/summary`), enabled: !!id });

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { user_id: string; pin?: string }) => api.post<User>("/auth/login", body),
    onSuccess: () => qc.invalidateQueries(),
  });
}
export function useLogout() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: () => api.post("/auth/logout"), onSuccess: () => qc.invalidateQueries() });
}
