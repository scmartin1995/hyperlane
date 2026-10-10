import { useMemo, useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis, Cell } from "recharts";
import { useProject } from "@/api/queries";
import { fmtDate, n1 } from "@/lib/format";
import { Select, Spinner } from "@/components/ui";
import { ChartCard, C, HLLegend, HLTooltip, MARK, axisProps, gridProps } from "./charts";
import { useCfd, useCycleTime, useThroughput } from "./hooks";

export function FlowTab({ pid }: { pid: string }) {
  const [days, setDays] = useState(60);
  const { data: project } = useProject(pid);
  const cfd = useCfd(pid, days);
  const ct = useCycleTime(pid, Math.max(days, 90));
  const tp = useThroughput(pid, Math.max(4, Math.round(days / 7)));
  const states = useMemo(() => [...(project?.workflow ?? [])].reverse(), [project]); // done at the bottom of the stack
  const cfdRows = (cfd.data ?? []).map((p) => [fmtDate(p.date), ...states.map((s) => Number(p[s.key] ?? 0))]);
  const ctPts = (ct.data?.points ?? []).map((p) => ({ ...p, t: new Date(p.completed_at).getTime() }));

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-xs"><span className="eyebrow">Window</span>
        <Select className="h-8 !w-auto" value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Date range">{[30, 60, 90, 180].map((d) => <option key={d} value={d}>Last {d} days</option>)}</Select></div>

      <ChartCard eyebrow="Cumulative flow" title="Items per workflow state" help="Stacked count of items in each state over time; widening bands mean work is piling up in that state." height={300}
        table={{ columns: ["Date", ...states.map((s) => s.name)], rows: cfdRows }} empty={!cfd.isLoading && !cfd.data?.length ? "No status history in this window yet." : undefined}>
        {cfd.isLoading ? <Center /> : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={cfd.data ?? []} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
              <CartesianGrid {...gridProps} /><XAxis dataKey="date" tickFormatter={(d: string) => fmtDate(d)} {...axisProps} minTickGap={28} /><YAxis {...axisProps} allowDecimals={false} />
              <Tooltip content={<HLTooltip title={(l) => fmtDate(String(l), "EEE, MMM d")} />} cursor={{ stroke: C.grid }} /><HLLegend />
              {states.map((s) => <Area key={s.key} type="monotone" dataKey={s.key} name={s.name} stackId="1" stroke={s.color || `var(--cat-${s.category})`} fill={s.color || `var(--cat-${s.category})`} fillOpacity={0.35} strokeWidth={1} isAnimationActive={false} />)}
            </AreaChart>
          </ResponsiveContainer>
        )}
      </ChartCard>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard eyebrow="Cycle time" title={<>Days to finish <span className="text-text-3 text-xs font-normal">p50 {n1(ct.data?.p50)} · p85 {n1(ct.data?.p85)}</span></>} help="Each dot is a finished item: when it finished vs how many days it took from start to done. Lines mark the 50th and 85th percentiles."
          table={{ columns: ["Key", "Title", "Done", "Cycle days", "Lead days"], rows: (ct.data?.points ?? []).map((p) => [p.key, p.title, fmtDate(p.completed_at), p.cycle_days, p.lead_days]) }} empty={!ct.isLoading && !ct.data?.points.length ? "Finish a few items to see cycle times." : undefined}>
          {ct.isLoading ? <Center /> : (
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tickFormatter={(t: number) => fmtDate(new Date(t).toISOString())} {...axisProps} name="Done" />
                <YAxis dataKey="cycle_days" type="number" {...axisProps} name="Days" allowDecimals={false} /><ZAxis range={[60, 60]} />
                <Tooltip content={<HLTooltip title={(_l, p) => { const r = p[0]?.payload as { key?: string; title?: string } | undefined; return r ? `${r.key} · ${r.title}` : ""; }} fmt={(v, name) => (name === "Done" ? fmtDate(new Date(Number(v)).toISOString()) : `${n1(Number(v))} d`)} />} cursor={{ stroke: C.grid }} />
                <ReferenceLine y={ct.data?.p50 ?? 0} stroke={C.gold} label={{ value: "p50", fill: C.axis, fontSize: 10, position: "insideTopRight" }} />
                <ReferenceLine y={ct.data?.p85 ?? 0} stroke={C.rust} label={{ value: "p85", fill: C.axis, fontSize: 10, position: "insideTopRight" }} />
                <Scatter data={ctPts} fill={C.teal} stroke={C.surface} strokeWidth={2} isAnimationActive={false}>{ctPts.map((p) => <Cell key={p.item_id} fill={p.cycle_days > (ct.data?.p85 ?? Infinity) ? C.rust : C.teal} />)}</Scatter>
              </ScatterChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard eyebrow="Throughput" title={<>Items finished per week <span className="text-text-3 text-xs font-normal">avg {n1(tp.data?.avg_count)}</span></>} help="How many items reached done each week; the line is the average over the window."
          table={{ columns: ["Week", "Items", "Points"], rows: (tp.data?.weeks ?? []).map((w) => [fmtDate(w.week_start), w.count, w.points]) }} empty={!tp.isLoading && !tp.data?.weeks.length ? "No finished work in this window." : undefined}>
          {tp.isLoading ? <Center /> : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={tp.data?.weeks ?? []} margin={{ top: 8, right: 12, left: -16, bottom: 0 }} barCategoryGap={4}>
                <CartesianGrid {...gridProps} /><XAxis dataKey="week_start" tickFormatter={(d: string) => fmtDate(d)} {...axisProps} /><YAxis {...axisProps} allowDecimals={false} />
                <Tooltip content={<HLTooltip title={(l) => `Week of ${fmtDate(String(l))}`} />} cursor={{ fill: "var(--surface-2)" }} />
                <ReferenceLine y={tp.data?.avg_count ?? 0} stroke={C.gold} label={{ value: "avg", fill: C.axis, fontSize: 10, position: "insideTopRight" }} />
                <Bar dataKey="count" name="Items" fill={C.teal} maxBarSize={MARK.bar} radius={MARK.radius} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
      </div>
    </div>
  );
}
export function Center() { return <div className="h-full flex items-center justify-center"><Spinner /></div>; }
