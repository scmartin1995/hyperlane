import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { n1 } from "@/lib/format";
import { Select, Stat } from "@/components/ui";
import { ChartCard, C, HLLegend, HLTooltip, MARK, Trend, axisProps, gridProps } from "./charts";
import { Center } from "./FlowTab";
import { useVelocity } from "./hooks";

export function VelocityTab({ pid }: { pid: string }) {
  const [last, setLast] = useState(8);
  const { data, isLoading } = useVelocity(pid, last);
  const rows = data ?? [];
  const avg = rows.length ? rows.reduce((a, r) => a + r.completed, 0) / rows.length : 0;
  const half = Math.floor(rows.length / 2);
  const trend = rows.length >= 4 ? rows.slice(half).reduce((a, r) => a + r.completed, 0) / (rows.length - half) - rows.slice(0, half).reduce((a, r) => a + r.completed, 0) / half : 0;
  const accuracy = rows.length ? rows.reduce((a, r) => a + (r.committed ? Math.min(1, r.completed / r.committed) : 1), 0) / rows.length : 0;
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-xs"><span className="eyebrow">Sprints</span><Select className="h-8 !w-auto" value={last} onChange={(e) => setLast(Number(e.target.value))} aria-label="Sprint count">{[4, 6, 8, 12, 20].map((d) => <option key={d} value={d}>Last {d}</option>)}</Select></div>
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Average velocity" value={n1(avg)} sub={<Trend value={trend} suffix=" pts recent vs earlier" />} />
        <Stat label="Commitment accuracy" value={`${Math.round(accuracy * 100)}%`} sub="completed ÷ committed, averaged" color={accuracy >= 0.85 ? "var(--green)" : accuracy >= 0.7 ? "var(--gold)" : "var(--rust-light)"} />
        <Stat label="Sprints closed" value={rows.length} sub="in this window" />
      </div>
      <ChartCard eyebrow="Velocity" title="Committed vs completed per sprint" help="Points committed at sprint start next to points actually finished; the line is the average completed." height={320}
        table={{ columns: ["Sprint", "Committed", "Completed"], rows: rows.map((r) => [r.sprint, r.committed, r.completed]) }} empty={!isLoading && rows.length === 0 ? "Close a sprint to start the velocity history." : undefined}>
        {isLoading ? <Center /> : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows} margin={{ top: 8, right: 12, left: -16, bottom: 0 }} barGap={2} barCategoryGap={12}>
              <CartesianGrid {...gridProps} /><XAxis dataKey="sprint" {...axisProps} /><YAxis {...axisProps} allowDecimals={false} />
              <Tooltip content={<HLTooltip />} cursor={{ fill: "var(--surface-2)" }} /><HLLegend />
              <ReferenceLine y={avg} stroke={C.gold} label={{ value: `avg ${n1(avg)}`, fill: C.axis, fontSize: 10, position: "insideTopRight" }} />
              <Bar dataKey="committed" name="Committed" fill={C.smoke} maxBarSize={MARK.bar} radius={MARK.radius} isAnimationActive={false} />
              <Bar dataKey="completed" name="Completed" fill={C.teal} maxBarSize={MARK.bar} radius={MARK.radius} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </ChartCard>
    </div>
  );
}
