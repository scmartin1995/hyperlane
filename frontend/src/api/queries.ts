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

// ---- appended by frontend-b (sprints/reports/people/action-items/intake/chat/settings) ----
import type { AgentStatus, IntegrationsStatus, Sprint, ActionItem } from "./types";
export const useAgentStatus = () => useQuery({ queryKey: qk.agentStatus, queryFn: () => api.get<AgentStatus>("/agent/status"), staleTime: 30_000 });
export const useIntegrationsStatus = () => useQuery({ queryKey: qk.integrations, queryFn: () => api.get<IntegrationsStatus>("/integrations/status") });
export const useSprintList = (pid: string | null | undefined, state?: Sprint["state"]) =>
  useQuery({ queryKey: [...qk.sprints(pid ?? ""), state ?? "all"] as const, queryFn: () => api.get<Sprint[]>(`/projects/${pid}/sprints${state ? `?state=${state}` : ""}`), enabled: !!pid });
export const useSprint = (id: string | undefined) => useQuery({ queryKey: qk.sprint(id ?? ""), queryFn: () => api.get<Sprint>(`/sprints/${id}`), enabled: !!id });
export const useMyActionItems = (includeDone = true) =>
  useQuery({ queryKey: [...qk.actionItems, includeDone] as const, queryFn: () => api.get<ActionItem[]>(`/me/action-items?include_done=${includeDone}`) });

// ---- appended by frontend-a: generic read hooks used by Home (and reusable elsewhere) ----
export const useMetricsOverview = (pid: string | undefined) =>
  useQuery({ queryKey: qk.metrics(pid ?? "", "overview"), queryFn: () => api.get<import("./types").MetricsOverview>(`/projects/${pid}/metrics/overview`), enabled: !!pid, retry: false });
export const useMeOverview = () =>
  useQuery({ queryKey: [...qk.me, "overview"] as const, queryFn: () => api.get<import("./types").MeOverview>("/me/overview") });
export const useProjectActivity = (pid: string | undefined, limit = 20) =>
  useQuery({ queryKey: [...qk.activity(pid ?? ""), { limit }] as const, queryFn: () => api.get<import("./types").Activity[]>(`/projects/${pid}/activity?limit=${limit}`), enabled: !!pid });

import type { TriageItem, TriageResult } from "./types";
export const useTriage = (pid: string | undefined) => useQuery({ queryKey: ["triage", pid ?? ""], queryFn: () => api.get<TriageItem[]>(`/projects/${pid}/triage`), enabled: !!pid });
export function useTriageAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: string; action: "accept" | "escalate" | "decline" | "snooze"; type?: string; sprint_id?: string; until?: string; reason?: string; create_children?: boolean }) => api.post<TriageResult>(`/items/${v.id}/triage`, v),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["triage"] }); qc.invalidateQueries({ queryKey: ["items"] }); qc.invalidateQueries({ queryKey: ["item"] }); qc.invalidateQueries({ queryKey: ["intake"] }); },
  });
}
export function useMessageRequester() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (v: { id: string; body: string }) => api.post(`/items/${v.id}/message-requester`, { body: v.body }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["item"] }); qc.invalidateQueries({ queryKey: ["triage"] }); } });
}
