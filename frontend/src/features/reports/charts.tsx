// Chart helpers for the Telemetry pages. Follows the dataviz method: thin marks, solid hairline grid, legend for >=2 series,
// colors from the design tokens (identity follows the entity, never the rank), a data-table twin behind every chart.
import { useState, type ReactNode } from "react";
import { Legend, type LegendPayload } from "recharts";
import { Table2, BarChart3 } from "lucide-react";
import { IconButton, cn } from "@/components/ui";
import { Help } from "@/features/sprints/common";

/* ---- theme constants ---- */
export const C = {
  gold: "var(--gold)", teal: "var(--teal)", rust: "var(--rust-light)", rustDeep: "var(--rust)", purple: "var(--purple-light)", green: "var(--green)",
  smoke: "var(--smoke)", grid: "var(--border)", axis: "var(--text-3)", surface: "var(--surface)",
} as const;
export const MARK = { line: 2, dot: 4, bar: 22, radius: [4, 4, 0, 0] as [number, number, number, number], areaOpacity: 0.12 } as const;
export const gridProps = { stroke: C.grid, strokeDasharray: undefined, vertical: false } as const;
export const axisProps = { stroke: C.grid, tick: { fill: C.axis, fontSize: 11, fontFamily: "var(--font-mono)" }, tickLine: false, axisLine: { stroke: C.grid } } as const;
export const statusColor = (s: "good" | "warn" | "bad") => (s === "good" ? C.green : s === "warn" ? C.gold : C.rust);
export const spiColor = (v: number) => (v >= 0.97 ? C.green : v >= 0.9 ? C.gold : C.rust);

/* ---- tooltip (styled like .panel) ---- */
type TipEntry = { name?: unknown; value?: unknown; color?: string; dataKey?: unknown; payload?: Record<string, unknown> };
export function HLTooltip({ active, payload, label, fmt, title }: { active?: boolean; payload?: ReadonlyArray<TipEntry>; label?: unknown; fmt?: (v: unknown, name: string) => ReactNode; title?: (label: unknown, payload: ReadonlyArray<TipEntry>) => ReactNode }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="panel p-2.5 text-xs min-w-[140px] shadow-xl animate-pop">
      <div className="eyebrow mb-1">{title ? title(label, payload) : String(label ?? "")}</div>
      {payload.map((p, i) => (
        <div key={i} className="flex items-center justify-between gap-4 py-0.5">
          <span className="inline-flex items-center gap-1.5 text-text-2"><span className="w-2 h-2 rounded-full shrink-0" style={{ background: p.color ?? C.smoke }} />{String(p.name ?? p.dataKey ?? "")}</span>
          <span className="num text-text">{fmt ? fmt(p.value, String(p.name ?? p.dataKey ?? "")) : typeof p.value === "number" ? fmtNum(p.value) : String(p.value ?? "")}</span>
        </div>
      ))}
    </div>
  );
}
export const fmtNum = (v: number) => (Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 1 }));

/* ---- legend ---- */
export function HLLegend() {
  return <Legend verticalAlign="top" align="right" height={26} iconType="circle" iconSize={8} formatter={(v: string) => <span className="text-[11px] text-text-2 font-display tracking-wide">{v}</span>} />;
}
export const legendPayload = (items: { value: string; color: string; type?: LegendPayload["type"] }[]): LegendPayload[] => items.map((i) => ({ value: i.value, color: i.color, type: i.type ?? "circle", id: i.value }));

/* ---- card wrapper with "?" help + table twin ---- */
export function ChartCard({ title, eyebrow, help, children, actions, table, className, height = 260, empty }: {
  title: ReactNode; eyebrow?: ReactNode; help: string; children: ReactNode; actions?: ReactNode; className?: string; height?: number;
  table?: { columns: string[]; rows: (string | number | null | undefined)[][] }; empty?: ReactNode | false;
}) {
  const [showTable, setShowTable] = useState(false);
  return (
    <section className={cn("panel p-4 min-w-0", className)}>
      <header className="flex items-start justify-between gap-3 mb-2">
        <div>
          {eyebrow && <div className="eyebrow">{eyebrow}</div>}
          <h2 className="text-base leading-tight inline-flex items-center gap-2">{title}<Help text={help} /></h2>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {actions}
          {table && <IconButton icon={showTable ? BarChart3 : Table2} label={showTable ? "Show chart" : "Show data table"} onClick={() => setShowTable((s) => !s)} />}
        </div>
      </header>
      {empty ? (
        <div className="flex items-center justify-center text-center text-sm text-text-3 border border-dashed border-border-strong rounded-[10px]" style={{ height }}>{empty}</div>
      ) : showTable && table ? (
        <div className="overflow-auto" style={{ maxHeight: height }}>
          <table className="w-full text-xs">
            <thead><tr>{table.columns.map((c) => <th key={c} className="text-left eyebrow py-1 pr-3 sticky top-0 bg-surface">{c}</th>)}</tr></thead>
            <tbody>{table.rows.map((r, i) => <tr key={i} className="border-t border-border">{r.map((v, j) => <td key={j} className={cn("py-1 pr-3", j > 0 && "num")}>{v == null ? "–" : typeof v === "number" ? fmtNum(v) : v}</td>)}</tr>)}</tbody>
          </table>
        </div>
      ) : (
        <div style={{ height }} className="w-full">{children}</div>
      )}
    </section>
  );
}

/* ---- health ring (SVG) ---- */
export function HealthRing({ score, label, size = 120 }: { score: number; label: string; size?: number }) {
  const r = (size - 12) / 2, c = 2 * Math.PI * r;
  const color = score >= 75 ? C.green : score >= 50 ? C.gold : C.rust;
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }} role="img" aria-label={`Health ${score} of 100, ${label}`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-3)" strokeWidth={8} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={8} strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - Math.max(0, Math.min(100, score)) / 100)} style={{ transition: "stroke-dashoffset .8s var(--ease-out)" }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center"><span className="text-3xl font-bold leading-none font-display">{Math.round(score)}</span><span className="eyebrow mt-1">{label}</span></div>
    </div>
  );
}

/* ---- tiny sparkline (SVG, no axes) ---- */
export function Sparkline({ series, width = 120, height = 32, colors = [C.smoke, C.teal] }: { series: number[][]; width?: number; height?: number; colors?: string[] }) {
  const all = series.flat();
  if (!all.length) return null;
  const max = Math.max(1, ...all), n = Math.max(...series.map((s) => s.length));
  const x = (i: number) => (n <= 1 ? width / 2 : (i / (n - 1)) * (width - 4) + 2);
  const y = (v: number) => height - 2 - (v / max) * (height - 4);
  return (
    <svg width={width} height={height} aria-hidden>
      {series.map((s, si) => <polyline key={si} fill="none" stroke={colors[si % colors.length]} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" points={s.map((v, i) => `${x(i)},${y(v)}`).join(" ")} />)}
      {series.map((s, si) => s.length ? <circle key={`d${si}`} cx={x(s.length - 1)} cy={y(s[s.length - 1])} r={3} fill={colors[si % colors.length]} stroke={C.surface} strokeWidth={2} /> : null)}
    </svg>
  );
}

/* ---- trend arrow for stat tiles ---- */
export function Trend({ value, goodUp = true, suffix = "" }: { value: number; goodUp?: boolean; suffix?: string }) {
  if (!value) return <span className="text-text-3">→ flat</span>;
  const up = value > 0, good = up === goodUp;
  return <span style={{ color: good ? C.green : C.rust }} className="num">{up ? "↑" : "↓"} {Math.abs(value).toLocaleString(undefined, { maximumFractionDigits: 1 })}{suffix}</span>;
}
