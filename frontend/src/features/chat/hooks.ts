import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { qk } from "@/api/queries";
import type { ChatThread } from "@/api/types";

export const MODES = [
  { key: "analyst", label: "Analyst", hint: "Ask about status, risks, metrics" },
  { key: "backlog", label: "Backlog builder", hint: "Draft epics → features → stories" },
  { key: "planning", label: "Sprint planning", hint: "What to pull, who's loaded" },
  { key: "retro", label: "Retro", hint: "Summaries and actions" },
] as const;
export type Mode = (typeof MODES)[number]["key"];

export const useThreads = () => useQuery({ queryKey: qk.chatThreads, queryFn: () => api.get<ChatThread[]>("/chat/threads") });
export const useThread = (id: string | null) => useQuery({ queryKey: qk.chatThread(id ?? ""), queryFn: () => api.get<ChatThread>(`/chat/threads/${id}`), enabled: !!id });
export function useThreadMutations() {
  const qc = useQueryClient();
  return {
    create: useMutation({ mutationFn: (b: { project_id?: string | null; mode?: string; context?: Record<string, unknown>; title?: string }) => api.post<ChatThread>("/chat/threads", b), onSuccess: () => qc.invalidateQueries({ queryKey: qk.chatThreads }) }),
    remove: useMutation({ mutationFn: (id: string) => api.delete(`/chat/threads/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: qk.chatThreads }) }),
  };
}
