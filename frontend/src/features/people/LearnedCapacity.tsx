import { Progress, Skeleton } from "@/components/ui";
import { n1 } from "@/lib/format";
import { Sparkline, C } from "@/features/reports/charts";
import { Help } from "@/features/sprints/common";
import { useProjectCapacity } from "./hooks";

export function LearnedCapacity({ pid, userId }: { pid: string; userId: string }) {
  const { data, isLoading } = useProjectCapacity(pid);
  const p = data?.find((x) => x.user_id === userId);
  return (
    <section className="panel panel-cut p-4">
      <div className="hairline mb-3" />
      <div className="eyebrow">Learned capacity <Help text="What the planner has learned from closed sprints in this project. More sprints → higher confidence." /></div>
      <h2 className="text-base mb-3">What the planner knows</h2>
      {isLoading ? <Skeleton className="h-24" /> : !p || p.sprints_observed === 0 ? <p className="text-sm text-text-3">No history yet. Close a sprint with this person's work in it and the planner starts learning.</p> : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
            <div><div className="eyebrow">Avg points</div><div className="text-xl font-display font-bold">{n1(p.avg_points)}</div><div className="text-[11px] text-text-3">±{n1(p.stddev_points)} per sprint</div></div>
            <div><div className="eyebrow">Throughput</div><div className="text-xl font-display font-bold">{n1(p.avg_count)}</div><div className="text-[11px] text-text-3">items per sprint</div></div>
            <div><div className="eyebrow">Accuracy</div><div className="text-xl font-display font-bold" style={{ color: p.commitment_accuracy >= 0.85 ? C.green : p.commitment_accuracy >= 0.7 ? C.gold : C.rust }}>{Math.round(p.commitment_accuracy * 100)}%</div><div className="text-[11px] text-text-3">completed ÷ planned</div></div>
            <div><div className="eyebrow">Pts / hour</div><div className="text-xl font-display font-bold">{n1(p.points_per_hour)}</div><div className="text-[11px] text-text-3">{p.sprints_observed} sprints observed</div></div>
          </div>
          <div className="flex items-center gap-3 mb-3"><span className="eyebrow w-20">Confidence</span><div className="flex-1"><Progress value={p.confidence * 100} color={p.confidence > 0.6 ? "var(--green)" : "var(--gold)"} /></div><span className="num text-xs">{Math.round(p.confidence * 100)}%</span></div>
          {p.history.length > 0 && (
            <div className="flex items-center gap-3 mb-3">
              <Sparkline series={[p.history.map((h) => h.planned), p.history.map((h) => h.completed)]} width={180} height={40} colors={[C.smoke, C.teal]} />
              <div className="text-[11px] text-text-3"><span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full" style={{ background: C.smoke }} /> planned</span> · <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full" style={{ background: C.teal }} /> completed</span><div>{p.history.map((h) => h.sprint_name ?? "").filter(Boolean).slice(-3).join(" · ")}</div></div>
            </div>
          )}
          {p.insights.length > 0 && <ul className="text-sm space-y-1 list-disc pl-5 text-text-2">{p.insights.map((i, n) => <li key={n}>{i}</li>)}</ul>}
        </>
      )}
    </section>
  );
}
