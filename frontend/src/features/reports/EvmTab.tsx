import { useEffect, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Camera, Lock } from "lucide-react";
import type { EvmConfig } from "@/api/types";
import { useProject } from "@/api/queries";
import { fmtDate, fmtDateTime, money, n1 } from "@/lib/format";
import { Badge, Button, EmptyState, Field, Input, Progress, Select, Skeleton, Toggle, toast } from "@/components/ui";
import { ChartCard, C, HLLegend, HLTooltip, MARK, axisProps, gridProps, spiColor } from "./charts";
import { Center } from "./FlowTab";
import { useEvm, useEvmMutations, useEvmSnapshots } from "./hooks";

const KPI_HELP: Record<string, string> = {
  SPI: "Schedule performance: earned ÷ planned value. Below 1 means behind schedule.", CPI: "Cost performance: earned value ÷ actual cost. Below 1 means over budget.",
  SV: "Schedule variance: earned − planned value (money).", CV: "Cost variance: earned value − actual cost.",
  EAC: "Estimate at completion: what the whole thing will likely cost at current performance.", ETC: "Estimate to complete: what's left to spend.",
  VAC: "Variance at completion: budget − EAC. Negative means overrun.", TCPI: "To-complete performance index: efficiency needed from here on to hit the budget.",
};

export function EvmTab({ pid }: { pid: string }) {
  const { data: r, isLoading, isError } = useEvm(pid);
  const { data: project } = useProject(pid);
  const m = useEvmMutations(pid);
  const configured = !!r && r.status !== "not_configured" && r.config.enabled;
  const snaps = useEvmSnapshots(pid, configured);
  if (isLoading) return <div className="space-y-3"><Skeleton className="h-28" /><Skeleton className="h-64" /></div>;
  if (isError) return <EmptyState icon="⚠️" title="Earned value unavailable" body="The server couldn't compute the EVM report." />;
  if (!configured) return <EvmSetup config={r?.config ?? project?.evm} onSave={(c) => m.config.mutate(c, { onSuccess: () => toast.success("EVM configured", "Lock the baseline when scope is settled."), onError: (e) => toast.error("Couldn't save", (e as Error).message) })} saving={m.config.isPending}
    onBaseline={() => m.baseline.mutate(undefined, { onSuccess: () => toast.fun("Baseline locked", "PV now has something to measure against."), onError: (e) => toast.error("Couldn't lock baseline", (e as Error).message) })} baselining={m.baseline.isPending} />;
  const cur = r.config.currency || "USD";
  const $ = (v: number) => money(v, cur);
  const statusColor = r.status === "on_track" ? C.green : r.status === "at_risk" ? C.gold : C.rust;
  const kpis: [string, string, string | undefined][] = [["SPI", n1(r.spi), spiColor(r.spi)], ["CPI", n1(r.cpi), spiColor(r.cpi)], ["SV", $(r.sv), r.sv < 0 ? C.rust : C.green], ["CV", $(r.cv), r.cv < 0 ? C.rust : C.green], ["EAC", $(r.eac), undefined], ["ETC", $(r.etc), undefined], ["VAC", $(r.vac), r.vac < 0 ? C.rust : C.green], ["TCPI", n1(r.tcpi), r.tcpi > 1.1 ? C.rust : undefined]];
  return (
    <div className="space-y-4">
      <div className="panel panel-cut p-4 flex flex-wrap items-center gap-4">
        <div className="hairline absolute top-0 left-0 right-0" />
        <div className="min-w-0 flex-1"><div className="eyebrow">Earned value · as of {fmtDate(r.as_of)}</div><div className="flex items-center gap-2"><h2 className="text-base">Budget {$(r.bac)}</h2><Badge color={statusColor} dot>{r.status.replace("_", " ")}</Badge>{!r.config.baseline_locked_at && <Badge color="var(--gold)">baseline not locked</Badge>}</div><p className="text-sm text-text-2 mt-1">{r.narrative}</p></div>
        <div className="flex items-center gap-2">
          {!r.config.baseline_locked_at && <Button variant="outline" icon={Lock} loading={m.baseline.isPending} onClick={() => m.baseline.mutate(undefined, { onSuccess: () => toast.fun("Baseline locked"), onError: (e) => toast.error("Couldn't lock baseline", (e as Error).message) })}>Lock baseline</Button>}
          <Button variant="teal" icon={Camera} loading={m.snapshot.isPending} onClick={() => m.snapshot.mutate(undefined, { onSuccess: () => { toast.success("Snapshot saved"); snaps.refetch(); }, onError: (e) => toast.error("Couldn't snapshot", (e as Error).message) })}>Snapshot now</Button>
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {kpis.map(([k, v, color]) => <div key={k} className="panel p-3.5" title={KPI_HELP[k]}><div className="eyebrow">{k}</div><div className="text-xl font-display font-bold mt-1" style={{ color }}>{v}</div><div className="text-[11px] text-text-3 mt-1 line-clamp-1">{KPI_HELP[k]}</div></div>)}
      </div>
      <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
        <ChartCard eyebrow="S-curve" title="Planned · earned · actual" help="Planned value is the budgeted schedule; earned value is what's been delivered; actual cost is what it has cost so far." height={300}
          table={{ columns: ["Date", "PV", "EV", "AC"], rows: r.series.map((p) => [fmtDate(p.date), p.pv, p.ev, p.ac]) }} empty={r.series.length === 0 ? "No data points yet — take a snapshot." : undefined}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={r.series} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid {...gridProps} /><XAxis dataKey="date" tickFormatter={(d: string) => fmtDate(d)} {...axisProps} minTickGap={28} /><YAxis {...axisProps} tickFormatter={(v: number) => (v >= 1000 ? `${Math.round(v / 1000)}k` : String(v))} />
              <Tooltip content={<HLTooltip fmt={(v) => $(Number(v))} title={(l) => fmtDate(String(l), "MMM d, yyyy")} />} cursor={{ stroke: C.grid }} /><HLLegend />
              <Area type="monotone" dataKey="pv" name="Planned (PV)" stroke={C.smoke} fill={C.smoke} fillOpacity={MARK.areaOpacity} strokeWidth={MARK.line} dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="ev" name="Earned (EV)" stroke={C.teal} strokeWidth={MARK.line} dot={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="ac" name="Actual (AC)" stroke={C.rust} strokeWidth={MARK.line} dot={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>
        <section className="panel p-4 space-y-3">
          <div className="eyebrow">Progress</div>
          {[["Complete", r.pct_complete, C.green], ["Planned", r.pct_planned, C.smoke], ["Spent", r.pct_spent, C.rust]].map(([l, v, c]) => <div key={String(l)}><div className="flex justify-between text-xs mb-1"><span>{l}</span><span className="num">{Math.round(Number(v))}%</span></div><Progress value={Number(v)} color={String(c)} /></div>)}
          <div className="pt-2 border-t border-border text-sm"><div className="eyebrow">Forecast end</div><div className="font-display font-bold text-lg">{r.forecast_end_date ? fmtDate(r.forecast_end_date, "MMM d, yyyy") : "–"}</div><div className="text-[11px] text-text-3">planned {r.config.end_date ? fmtDate(r.config.end_date, "MMM d, yyyy") : "–"}</div></div>
        </section>
      </div>
      <section className="panel overflow-hidden">
        <header className="px-4 pt-4 pb-2"><div className="eyebrow">Snapshots</div><h2 className="text-base">History</h2></header>
        {snaps.isLoading ? <div className="p-4"><Center /></div> : !snaps.data?.length ? <p className="px-4 pb-4 text-sm text-text-3">No snapshots yet. A daily job records one; use "Snapshot now" to add one immediately.</p> : (
          <table className="w-full text-sm"><thead><tr className="text-left border-y border-border bg-surface-2/50"><th className="px-4 py-2 eyebrow">Date</th><th className="px-2 py-2 eyebrow text-right">PV</th><th className="px-2 py-2 eyebrow text-right">EV</th><th className="px-2 py-2 eyebrow text-right">AC</th><th className="px-2 py-2 eyebrow text-right">SPI</th><th className="px-4 py-2 eyebrow text-right">CPI</th></tr></thead>
            <tbody>{[...snaps.data].reverse().map((s) => <tr key={s.id} className="border-b border-border"><td className="px-4 py-1.5">{fmtDateTime(String(s.created_at ?? s.date))}</td><td className="px-2 py-1.5 num text-right">{$(s.pv)}</td><td className="px-2 py-1.5 num text-right">{$(s.ev)}</td><td className="px-2 py-1.5 num text-right">{$(s.ac)}</td><td className="px-2 py-1.5 num text-right">{s.spi != null ? n1(s.spi) : s.pv ? n1(s.ev / s.pv) : "–"}</td><td className="px-4 py-1.5 num text-right">{s.cpi != null ? n1(s.cpi) : s.ac ? n1(s.ev / s.ac) : "–"}</td></tr>)}</tbody></table>
        )}
      </section>
    </div>
  );
}

function EvmSetup({ config, onSave, saving, onBaseline, baselining }: { config: EvmConfig | undefined; onSave: (c: Partial<EvmConfig>) => void; saving: boolean; onBaseline: () => void; baselining: boolean }) {
  const [c, setC] = useState<Partial<EvmConfig>>({ enabled: true, currency: "USD", bac: 0, cost_per_point: 0, cost_per_hour: 0, planned_sprints: 6, method: "points", start_date: null, end_date: null });
  useEffect(() => { if (config) setC({ ...config, enabled: true }); }, [config]);
  const set = <K extends keyof EvmConfig>(k: K, v: EvmConfig[K]) => setC((p) => ({ ...p, [k]: v }));
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <section className="panel panel-cut p-5">
        <div className="hairline mb-4" /><div className="eyebrow">Earned value setup</div><h2 className="text-lg">Put a budget on the track</h2>
        <p className="text-sm text-text-2 mt-1 mb-4">EVM compares planned, earned and actual value over time. Set a budget and cost rates, then lock a baseline once scope is agreed.</p>
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); onSave(c); }}>
          <Field label="Budget at completion (BAC)" required><Input type="number" min={0} className="num" value={c.bac ?? 0} onChange={(e) => set("bac", Number(e.target.value))} /></Field>
          <Field label="Currency"><Input value={c.currency ?? "USD"} maxLength={3} onChange={(e) => set("currency", e.target.value.toUpperCase())} /></Field>
          <Field label="Method"><Select value={c.method ?? "points"} onChange={(e) => set("method", e.target.value as EvmConfig["method"])}><option value="points">Story points</option><option value="hours">Hours</option><option value="count">Item count</option></Select></Field>
          <Field label="Planned sprints"><Input type="number" min={1} className="num" value={c.planned_sprints ?? 1} onChange={(e) => set("planned_sprints", Number(e.target.value))} /></Field>
          <Field label="Cost per point"><Input type="number" min={0} className="num" value={c.cost_per_point ?? 0} onChange={(e) => set("cost_per_point", Number(e.target.value))} /></Field>
          <Field label="Cost per hour"><Input type="number" min={0} className="num" value={c.cost_per_hour ?? 0} onChange={(e) => set("cost_per_hour", Number(e.target.value))} /></Field>
          <Field label="Start"><Input type="date" value={c.start_date ?? ""} onChange={(e) => set("start_date", e.target.value || null)} /></Field>
          <Field label="End"><Input type="date" value={c.end_date ?? ""} onChange={(e) => set("end_date", e.target.value || null)} /></Field>
          <div className="sm:col-span-2 flex items-center justify-between pt-2"><Toggle checked={c.enabled ?? true} onChange={(v) => set("enabled", v)} label="Enabled" /><Button type="submit" variant="primary" loading={saving}>Save configuration</Button></div>
        </form>
      </section>
      <section className="panel p-4 self-start">
        <div className="eyebrow">Then</div><h3 className="font-display font-bold">Lock the baseline</h3>
        <p className="text-sm text-text-3 mt-1 mb-3">Freezes planned points from the current scope, the sprint count and dates. PV is measured against this.</p>
        <Button icon={Lock} variant="outline" loading={baselining} onClick={onBaseline} disabled={!config?.enabled}>Lock baseline</Button>
        {!config?.enabled && <p className="text-[11px] text-text-3 mt-2">Save the configuration first.</p>}
      </section>
    </div>
  );
}
