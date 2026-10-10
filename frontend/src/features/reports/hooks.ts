import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { qk } from "@/api/queries";
import type { CfdPoint, CycleTimeReport, EvmConfig, EvmReport, Forecast, MetricsOverview, Project, ThroughputReport } from "@/api/types";

export type EvmSnapshot = { id: string; project_id: string; date: string; pv: number; ev: number; ac: number; spi?: number; cpi?: number; created_at?: string; [k: string]: unknown };

export const useMetricsOverview = (pid: string) => useQuery({ queryKey: qk.metrics(pid, "overview"), queryFn: () => api.get<MetricsOverview>(`/projects/${pid}/metrics/overview`) });
export const useCfd = (pid: string, days: number) => useQuery({ queryKey: qk.metrics(pid, "cfd", { days }), queryFn: () => api.get<CfdPoint[]>(`/projects/${pid}/metrics/cfd?days=${days}`) });
export const useCycleTime = (pid: string, days: number) => useQuery({ queryKey: qk.metrics(pid, "cycle", { days }), queryFn: () => api.get<CycleTimeReport>(`/projects/${pid}/metrics/cycle-time?days=${days}`) });
export const useThroughput = (pid: string, weeks: number) => useQuery({ queryKey: qk.metrics(pid, "throughput", { weeks }), queryFn: () => api.get<ThroughputReport>(`/projects/${pid}/metrics/throughput?weeks=${weeks}`) });
export const useVelocity = (pid: string, last: number) => useQuery({ queryKey: qk.metrics(pid, "velocity", { last }), queryFn: () => api.get<MetricsOverview["velocity"]>(`/projects/${pid}/metrics/velocity?last=${last}`) });
export const useForecast = (pid: string, p: { mode: "how_many" | "when"; weeks: number; items: number; history_weeks: number }) =>
  useQuery({ queryKey: qk.metrics(pid, "forecast", p), queryFn: () => api.get<Forecast>(`/projects/${pid}/forecast?mode=${p.mode}&${p.mode === "how_many" ? `weeks=${p.weeks}` : `items=${p.items}`}&history_weeks=${p.history_weeks}&sims=5000`) });
export const useEvm = (pid: string) => useQuery({ queryKey: qk.evm(pid), queryFn: () => api.get<EvmReport>(`/projects/${pid}/evm`) });
export const useEvmSnapshots = (pid: string, enabled: boolean) => useQuery({ queryKey: [...qk.evm(pid), "snapshots"] as const, queryFn: () => api.get<EvmSnapshot[]>(`/projects/${pid}/evm/snapshots`), enabled });

export function useEvmMutations(pid: string) {
  const qc = useQueryClient();
  const done = () => { qc.invalidateQueries({ queryKey: qk.evm(pid) }); qc.invalidateQueries({ queryKey: qk.project(pid) }); };
  return {
    config: useMutation({ mutationFn: (c: Partial<EvmConfig>) => api.put<Project>(`/projects/${pid}/evm/config`, c), onSuccess: done }),
    baseline: useMutation({ mutationFn: () => api.post<Project>(`/projects/${pid}/evm/baseline`), onSuccess: done }),
    snapshot: useMutation({ mutationFn: () => api.post<EvmSnapshot>(`/projects/${pid}/evm/snapshot`), onSuccess: done }),
  };
}
