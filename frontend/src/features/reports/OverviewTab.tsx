import { Link } from "react-router-dom";
import type { MetricsOverview } from "@/api/types";
import { fmtDate, n1 } from "@/lib/format";
import { Badge, EmptyState, Progress, Skeleton, Stat } from "@/components/ui";
import { HealthRing, Trend, statusColor } from "./charts";
import { useMetricsOverview } from "./hooks";

export function OverviewTab({ pid }: { pid: string }) {
  const { data: m, isLoading, isError } = useMetricsOverview(pid);
  if (isLoading) return <div className="grid gap-3 md:grid-cols-3">{[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-24" />)}</div>;
  if (isError || !m) return <EmptyState icon="📊" title="No insights yet" body="Metrics appear once items move through the workflow." />;
  const sig = (s: MetricsOverview["health"]["signals"][number]) => s;
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <section className="panel panel-cut p-4 flex items-center gap-4 lg:row-span-2">
        <HealthRing score={m.health.score} label={m.health.label} />
        <div className="min-w-0 flex-1">
          <div className="eyebrow">Health · as of {fmtDate(m.as_of)}</div>
          <h2 className="text-base">Signals</h2>
          <ul className="mt-2 space-y-1.5">
            {m.health.signals.length === 0 && <li className="text-sm text-text-3">Not enough data for signals yet.</li>}
            {m.health.signals.map(sig).map((s) => (
              <li key={s.name} className="text-sm flex items-start gap-2"><span className="mt-1.5 w-2 h-2 rounded-full shrink-0" style={{ background: statusColor(s.status) }} aria-label={s.status} /><span><span className="font-display font-semibold">{s.name}</span> <span className="text-text-3">— {s.detail}</span></span></li>
            ))}
          </ul>
        </div>
      </section>
      <div className="lg:col-span-2 grid grid-cols-2 md:grid-cols-3 gap-3">
        <Stat tone="teal" label="Avg velocity" value={n1(m.avg_velocity)} sub={<Trend value={m.velocity_trend} suffix=" pts vs prior" />} />
        <Stat tone="purple" label="Throughput / wk" value={n1(m.throughput_per_week)} sub="items finished per week" />
        <Stat tone="dark" label="Cycle time p50 / p85" value={<>{n1(m.avg_cycle_time_days)}<span className="opacity-60 text-base"> / {n1(m.p85_cycle_time_days)}d</span></>} sub="days from start to done" />
        <Stat tone={m.wip_limit_breaches.length ? "rust" : "gold"} label="WIP" value={m.wip} sub={m.wip_limit_breaches.length ? <span className="text-rust-light">{m.wip_limit_breaches.map((b) => `${b.status} ${b.count}/${b.limit}`).join(" · ")}</span> : "within limits"} color={m.wip_limit_breaches.length ? "var(--rust-light)" : undefined} />
        <Stat tone="cream" label="Flow efficiency" value={m.flow_efficiency == null ? "–" : `${Math.round(m.flow_efficiency * 100)}%`} sub="active time ÷ total time" />
        <Stat tone={m.blocked + m.overdue > 0 ? "rust" : "cream"} label="Blocked · overdue" value={<>{m.blocked}<span className="opacity-60 text-base"> · {m.overdue}</span></>} sub="items needing a nudge" color={m.blocked + m.overdue > 0 ? "var(--gold)" : undefined} />
      </div>
      <section className="panel p-4 lg:col-span-2">
        <div className="flex items-center justify-between"><div><div className="eyebrow">Active sprint</div><h2 className="text-base">{m.active_sprint ? m.active_sprint.sprint.name : "No sprint running"}</h2></div>
          {m.active_sprint && <Badge color={m.active_sprint.on_track ? "var(--green)" : "var(--rust)"} dot>{m.active_sprint.on_track ? "on track" : "behind"}</Badge>}</div>
        {m.active_sprint ? (
          <div className="mt-3 space-y-2">
            <div><div className="flex justify-between text-xs mb-1"><span>Time elapsed</span><span className="num">{Math.round(m.active_sprint.pct_time)}% · {m.active_sprint.days_left}d left</span></div><Progress value={m.active_sprint.pct_time} color="var(--smoke)" /></div>
            <div><div className="flex justify-between text-xs mb-1"><span>Scope done</span><span className="num">{Math.round(m.active_sprint.pct_scope_done)}%</span></div><Progress value={m.active_sprint.pct_scope_done} color="var(--green)" /></div>
            <Link to={`/sprints/${m.active_sprint.sprint.id}`} className="text-xs">Open sprint →</Link>
          </div>
        ) : <p className="text-sm text-text-3 mt-2">Start a sprint from <Link to="/sprints">Sprints</Link> to track time vs scope here.</p>}
      </section>
    </div>
  );
}
