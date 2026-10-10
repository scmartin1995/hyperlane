// Project health strip: gauge + velocity/cycle time/WIP/blocked/overdue. Falls back to the project summary when metrics 404.
import { Activity, Clock, Gauge, Layers, AlertTriangle } from "lucide-react";
import type { MetricsOverview, ProjectSummary } from "@/api/types";
import { n1 } from "@/lib/format";
import { Skeleton, Stat, cn } from "@/components/ui";

export function HealthGauge({ score, label, size = 96 }: { score: number; label: string; size?: number }) {
  const r = (size - 12) / 2; const c = 2 * Math.PI * r; const pctv = Math.max(0, Math.min(100, score)); const arc = c * 0.75;
  const color = pctv >= 70 ? "var(--green)" : pctv >= 40 ? "var(--gold)" : "var(--rust)";
  return (
    <div className="relative grid place-items-center shrink-0" style={{ width: size, height: size }} role="img" aria-label={`Health ${Math.round(pctv)} — ${label}`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="rotate-[135deg]">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-3)" strokeWidth={8} strokeDasharray={`${arc} ${c}`} strokeLinecap="round" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={8} strokeDasharray={`${(arc * pctv) / 100} ${c}`} strokeLinecap="round" className="transition-[stroke-dasharray] duration-700" />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center leading-none"><span className="num text-2xl font-bold" style={{ color }}>{Math.round(pctv)}</span><span className="eyebrow mt-1 text-[9px]">{label}</span></div>
    </div>
  );
}

export function HealthStrip({ metrics, summary, loading, estimation }: { metrics: MetricsOverview | undefined; summary: ProjectSummary | undefined; loading: boolean; estimation?: string }) {
  if (loading) return <div className="grid grid-cols-2 md:grid-cols-5 gap-3">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-[84px]" />)}</div>;
  const unit = estimation === "hours" ? "h" : estimation === "throughput" ? " items" : " pts";
  if (!metrics) {
    // Fallback: the analytics endpoints aren't up yet (or the project is brand new). Use summary counts.
    const s = summary;
    return (
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div className="panel p-3.5 flex items-center gap-3 col-span-2 md:col-span-1"><HealthGauge score={s ? Math.round((s.done_items / Math.max(1, s.total_items)) * 100) : 0} label="done" size={72} /><div className="text-[11px] text-text-3">Insights warming up. Showing completion for now.</div></div>
        <Stat tone="teal" label="Items" value={<>{s?.done_items ?? 0}<span className="opacity-60 text-base">/{s?.total_items ?? 0}</span></>} sub="done / total" icon={Layers} />
        <Stat tone="dark" label="Points" value={<>{n1(s?.done_points)}<span className="opacity-60 text-base">/{n1(s?.total_points)}</span></>} sub="done / total" icon={Gauge} />
        <Stat tone={s?.blocked ? "rust" : "gold"} label="Blocked" value={s?.blocked ?? 0} icon={AlertTriangle} sub="need a push" />
        <Stat tone={s?.overdue ? "rust" : "cream"} label="Overdue" value={s?.overdue ?? 0} icon={Clock} sub="past due date" />
      </div>
    );
  }
  const m = metrics;
  const trend = m.velocity_trend;
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
      <div className="panel p-3.5 flex items-center gap-3 col-span-2 md:col-span-1">
        <HealthGauge score={m.health.score} label={m.health.label} size={80} />
        <ul className="text-[11px] space-y-0.5 min-w-0">{m.health.signals.slice(0, 3).map((s) => <li key={s.name} className="flex items-center gap-1.5 truncate" title={s.detail}><span className={cn("w-1.5 h-1.5 rounded-full shrink-0", s.status === "good" ? "bg-green" : s.status === "warn" ? "bg-gold" : "bg-rust")} /><span className="truncate text-text-2">{s.name}</span></li>)}</ul>
      </div>
      <Stat tone="teal" label="Velocity" value={<>{n1(m.avg_velocity)}<span className="opacity-60 text-sm">{unit}</span></>} icon={Activity} sub={<span className={cn(trend > 0 ? "text-green" : trend < 0 ? "text-rust-light" : "")}>{trend > 0 ? "▲" : trend < 0 ? "▼" : "■"} {n1(Math.abs(trend))} vs. last · {n1(m.throughput_per_week)}/wk</span>} />
      <Stat tone="dark" label="Cycle time" value={<>{n1(m.avg_cycle_time_days)}<span className="opacity-60 text-sm">d</span></>} icon={Clock} sub={<>p85 {n1(m.p85_cycle_time_days)}d{m.flow_efficiency != null && <> · flow {Math.round(m.flow_efficiency * 100)}%</>}</>} />
      <Stat tone={m.wip_limit_breaches.length ? "rust" : "gold"} label="WIP" value={m.wip} icon={Layers} sub={m.wip_limit_breaches.length ? `${m.wip_limit_breaches.map((b) => `${b.status} ${b.count}/${b.limit}`).join(", ")}` : "within limits"} />
      <Stat tone={m.blocked || m.overdue ? "rust" : "cream"} label="Blocked / overdue" value={<><span style={{ color: m.blocked ? "var(--rust-light)" : undefined }}>{m.blocked}</span><span className="opacity-60 text-base"> / </span><span style={{ color: m.overdue ? "var(--rust-light)" : undefined }}>{m.overdue}</span></>} icon={AlertTriangle} sub="need attention" />
    </div>
  );
}
