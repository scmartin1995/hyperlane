import type { IntakeRequirements } from "@/api/types";
import { priorityIcon } from "@/lib/format";
import { Badge, Progress } from "@/components/ui";

export function RequirementsCard({ req }: { req: IntakeRequirements }) {
  const has = Object.keys(req ?? {}).length > 0;
  const conf = req.confidence ?? 0;
  const List = ({ title, items, color }: { title: string; items?: string[]; color?: string }) => items?.length ? <div><div className="eyebrow" style={{ color }}>{title}</div><ul className="list-disc pl-4 text-sm space-y-0.5 mt-0.5">{items.map((x, i) => <li key={i}>{x}</li>)}</ul></div> : null;
  const Row = ({ title, text }: { title: string; text?: string }) => text ? <div><div className="eyebrow">{title}</div><p className="text-sm">{text}</p></div> : null;
  return (
    <section className="panel panel-cut p-4">
      <div className="hairline mb-3" />
      <div className="flex items-start justify-between gap-3 mb-3">
        <div><div className="eyebrow">Requirements</div><h2 className="text-base">What the assistant understood</h2></div>
        <div className="w-40"><div className="flex justify-between text-[11px] mb-1"><span className="eyebrow">Confidence</span><span className="num">{Math.round(conf * 100)}%</span></div><Progress value={conf * 100} color={conf >= 0.75 ? "var(--green)" : conf >= 0.5 ? "var(--gold)" : "var(--rust)"} /></div>
      </div>
      {!has ? <p className="text-sm text-text-3">Not analyzed yet. Run "Analyze" to draft requirements.</p> : (
        <div className="grid gap-3 sm:grid-cols-2">
          <Row title="Problem" text={req.problem} /><Row title="Desired outcome" text={req.outcome} /><Row title="Users" text={req.users} />
          <div className="flex flex-wrap gap-2 items-start">{req.priority && <Badge color={`var(--prio-${req.priority})`}>{priorityIcon[req.priority]} {req.priority}</Badge>}{req.urgency && <Badge>{req.urgency}</Badge>}</div>
          <List title="In scope" items={req.scope_in} color="var(--green)" /><List title="Out of scope" items={req.scope_out} color="var(--rust-light)" />
          <List title="Acceptance" items={req.acceptance} /><List title="Constraints" items={req.constraints} />
          {req.open_questions?.length ? <div className="sm:col-span-2 rounded-[8px] border border-gold/40 bg-gold/10 p-3"><div className="eyebrow text-gold">Open questions</div><ul className="list-disc pl-4 text-sm mt-1">{req.open_questions.map((q, i) => <li key={i}>{q}</li>)}</ul></div> : null}
        </div>
      )}
    </section>
  );
}
