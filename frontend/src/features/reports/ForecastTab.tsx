import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlertTriangle } from "lucide-react";
import { fmtDate } from "@/lib/format";
import { Field, Input, Tabs } from "@/components/ui";
import { ChartCard, C, HLTooltip, MARK, axisProps, gridProps } from "./charts";
import { Center } from "./FlowTab";
import { useForecast } from "./hooks";

export function ForecastTab({ pid }: { pid: string }) {
  const [mode, setMode] = useState<"how_many" | "when">("how_many");
  const [weeks, setWeeks] = useState(2); const [items, setItems] = useState(20); const [hist, setHist] = useState(12);
  const { data: f, isLoading } = useForecast(pid, { mode, weeks, items, history_weeks: hist });
  const hm = f?.how_many, wh = f?.when;
  const callouts = mode === "how_many" && hm ? [["p50", hm.p50], ["p70", hm.p70], ["p85", hm.p85], ["p95", hm.p95]] as const : wh ? [["p50", fmtDate(wh.p50_date)], ["p70", fmtDate(wh.p70_date)], ["p85", fmtDate(wh.p85_date)], ["p95", fmtDate(wh.p95_date)]] as const : [];
  const histo = mode === "how_many" ? (hm?.histogram ?? []).map((h) => ({ x: String(h.value), count: h.count })) : (wh?.histogram ?? []).map((h) => ({ x: fmtDate(h.date), count: h.count }));
  const marker = mode === "how_many" ? String(hm?.p85 ?? "") : fmtDate(wh?.p85_date);
  return (
    <div className="space-y-4">
      <div className="panel p-3 flex flex-wrap items-end gap-3">
        <Tabs value={mode} onChange={setMode} tabs={[{ key: "how_many", label: "How many items?" }, { key: "when", label: "When will N be done?" }]} />
        {mode === "how_many" ? <Field label="In the next (weeks)"><Input type="number" min={1} max={52} className="w-24 h-8 num" value={weeks} onChange={(e) => setWeeks(Math.max(1, Number(e.target.value)))} /></Field>
          : <Field label="Items to finish"><Input type="number" min={1} className="w-24 h-8 num" value={items} onChange={(e) => setItems(Math.max(1, Number(e.target.value)))} /></Field>}
        <Field label="History (weeks)"><Input type="number" min={2} max={52} className="w-24 h-8 num" value={hist} onChange={(e) => setHist(Math.max(2, Number(e.target.value)))} /></Field>
        <span className="text-xs text-text-3 ml-auto">{f ? `${f.simulations.toLocaleString()} simulations over ${f.history_weeks} weeks of throughput` : ""}</span>
      </div>
      {f?.warning && <div className="flex items-start gap-2 p-3 rounded-[10px] border border-gold/40 bg-gold/10 text-sm"><AlertTriangle size={16} className="text-gold shrink-0 mt-0.5" />{f.warning}</div>}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {callouts.map(([k, v], i) => (
          <div key={k} className="panel p-3.5"><div className="eyebrow">{k} {k === "p85" && "· plan on this"}</div><div className="text-2xl font-display font-bold mt-1" style={{ color: i === 2 ? C.gold : undefined }}>{v}</div><div className="text-[11px] text-text-3 mt-1">{mode === "how_many" ? `items in ${weeks}w, ${k.slice(1)}% likely` : `${items} items done by then, ${k.slice(1)}% likely`}</div></div>
        ))}
        {!f && !isLoading && <div className="col-span-full text-sm text-text-3">Forecast needs some throughput history first.</div>}
      </div>
      <ChartCard eyebrow="Monte Carlo" title={mode === "how_many" ? "Distribution of items finished" : "Distribution of finish dates"} help="Each bar is how many simulations landed on that outcome; the gold bar marks the 85th percentile." height={280}
        table={{ columns: [mode === "how_many" ? "Items" : "Date", "Simulations"], rows: histo.map((h) => [h.x, h.count]) }} empty={!isLoading && histo.length === 0 ? "Not enough throughput history to simulate." : undefined}>
        {isLoading ? <Center /> : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={histo} margin={{ top: 8, right: 12, left: -16, bottom: 0 }} barCategoryGap={2}>
              <CartesianGrid {...gridProps} /><XAxis dataKey="x" {...axisProps} minTickGap={16} /><YAxis {...axisProps} allowDecimals={false} />
              <Tooltip content={<HLTooltip />} cursor={{ fill: "var(--surface-2)" }} />
              <Bar dataKey="count" name="Simulations" fill={C.teal} maxBarSize={MARK.bar} radius={MARK.radius} isAnimationActive={false}>{histo.map((h) => <Cell key={h.x} fill={h.x === marker ? C.gold : C.teal} />)}</Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </ChartCard>
    </div>
  );
}
