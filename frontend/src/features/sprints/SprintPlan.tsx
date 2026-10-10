// Sprint planning: ① capacity → ② pick work → ③ commit.
import { useEffect, useMemo, useState } from "react";
import { Check, ChevronRight, Flag, Sparkles, RefreshCw } from "lucide-react";
import type { PlanSuggestion, Project, Sprint, SprintCapacity, WorkItem } from "@/api/types";
import { useUI } from "@/lib/store";
import { n1, pct, priorityIcon, typeOf } from "@/lib/format";
import { Avatar, Badge, Button, EmptyState, Input, Progress, Skeleton, celebrate, toast, cn } from "@/components/ui";
import { Help, ItemDrawer, LoadingRows } from "./common";
import { useCommitPlan, usePlanSuggest, usePutCapacity, useSprintCapacity } from "./hooks";

type Step = 1 | 2 | 3;
const STEPS: { n: Step; title: string; sub: string }[] = [{ n: 1, title: "Capacity", sub: "Who's racing and for how long" }, { n: 2, title: "Pick work", sub: "Fill the sprint to capacity" }, { n: 3, title: "Commit", sub: "Lock it in and go" }];

export function SprintPlan({ sprint, project, onStart }: { sprint: Sprint; project: Project | undefined; onStart: () => void }) {
  const [step, setStep] = useState<Step>(1);
  const [picked, setPicked] = useState<Set<string> | null>(null);
  const cap = useSprintCapacity(sprint.id);
  const suggest = usePlanSuggest(sprint.id, step >= 2);
  useEffect(() => { if (suggest.data && picked === null) setPicked(new Set(suggest.data.recommended_ids)); }, [suggest.data, picked]);

  if (sprint.state === "closed") return <EmptyState icon="🏁" title="This lap is over" body="Planning is for planned or active sprints. Check the retro instead." />;
  return (
    <div className="grid gap-4 lg:grid-cols-[220px_1fr]">
      <ol className="panel p-2 self-start space-y-1">
        {STEPS.map((s) => (
          <li key={s.n}><button onClick={() => setStep(s.n)} className={cn("w-full text-left flex items-center gap-3 px-3 py-2.5 rounded-[8px] transition-colors", step === s.n ? "bg-surface-2 text-gold" : "text-text-2 hover:bg-surface-2/60")}>
            <span className={cn("w-7 h-7 rounded-full border flex items-center justify-center font-display font-bold text-sm shrink-0", step === s.n ? "border-gold" : step > s.n ? "border-green text-green" : "border-border-strong")}>{step > s.n ? <Check size={14} /> : s.n}</span>
            <span className="leading-tight"><span className="block font-display font-semibold">{s.title}</span><span className="block text-[11px] text-text-3">{s.sub}</span></span>
          </button></li>
        ))}
      </ol>
      <div className="min-w-0">
        {step === 1 && <CapacityStep sprint={sprint} cap={cap.data} loading={cap.isLoading} error={cap.isError} onNext={() => setStep(2)} />}
        {step === 2 && <PickStep sprint={sprint} project={project} plan={suggest.data} loading={suggest.isLoading} error={suggest.isError} refetch={() => suggest.refetch()} picked={picked ?? new Set()} setPicked={setPicked} onBack={() => setStep(1)} onNext={() => setStep(3)} />}
        {step === 3 && <CommitStep sprint={sprint} plan={suggest.data} picked={picked ?? new Set()} onBack={() => setStep(2)} onStart={onStart} />}
      </div>
    </div>
  );
}

/* ---------- ① capacity ---------- */
function CapacityStep({ sprint, cap, loading, error, onNext }: { sprint: Sprint; cap: SprintCapacity | undefined; loading: boolean; error: boolean; onNext: () => void }) {
  const put = usePutCapacity(sprint.id);
  const [draft, setDraft] = useState<Record<string, number>>({});
  useEffect(() => { if (cap) setDraft(Object.fromEntries(cap.entries.map((e) => [e.user_id, e.days_off]))); }, [cap]);
  const dirty = cap?.entries.some((e) => draft[e.user_id] !== undefined && draft[e.user_id] !== e.days_off);
  const save = (then?: () => void) => put.mutate(cap!.entries.map((e) => ({ user_id: e.user_id, days_off: draft[e.user_id] ?? e.days_off })), { onSuccess: () => { toast.success("Capacity saved"); then?.(); }, onError: (e) => toast.error("Couldn't save capacity", (e as Error).message) });
  if (loading) return <LoadingRows n={4} />;
  if (error || !cap) return <EmptyState icon="⚠️" title="Capacity unavailable" body="The server couldn't compute capacity for this sprint." />;
  const unit = cap.method === "hours" ? "h" : cap.method === "throughput" ? " items" : " pts";
  const teamTotal = cap.method === "hours" ? cap.team_hours : cap.method === "throughput" ? cap.team_count : cap.team_points;
  const maxHours = Math.max(1, ...cap.entries.map((e) => e.available_hours + e.days_off * 8));
  return (
    <section className="panel p-0 overflow-hidden animate-in">
      <header className="px-4 pt-4 pb-3 flex items-start justify-between gap-3"><div><div className="eyebrow">Step 1 of 3</div><h2 className="text-base">Who's in the car this sprint?</h2><p className="text-xs text-text-3 mt-0.5">Set days off; hours and suggested {cap.method === "points" ? "points" : cap.method === "hours" ? "hours" : "throughput"} update from each person's learned profile.</p></div></header>
      {cap.entries.length === 0 ? <div className="p-4"><EmptyState icon="👥" title="No crew yet" body="Add people in Pit Crew to plan capacity." /></div> : (
        <table className="w-full text-sm">
          <thead><tr className="text-left border-y border-border bg-surface-2/50"><th className="px-4 py-2 eyebrow">Person</th><th className="px-2 py-2 eyebrow">Days off</th><th className="px-2 py-2 eyebrow text-right">Available</th><th className="px-2 py-2 eyebrow text-right">Suggested</th><th className="px-2 py-2 eyebrow">Confidence <Help text="How much history the suggestion is based on." /></th></tr></thead>
          <tbody>
            {cap.entries.map((e) => {
              const p = e.profile;
              const tip = p ? `Learned from ${p.sprints_observed} sprint${p.sprints_observed === 1 ? "" : "s"}, commitment accuracy ${Math.round(p.commitment_accuracy * 100)}%` : "No history yet — using hours × focus factor";
              return (
                <tr key={e.user_id} className="border-b border-border">
                  <td className="px-4 py-2"><span className="inline-flex items-center gap-2"><Avatar user={e.user} size={24} /><span><span className="block font-display font-semibold leading-tight">{e.user.name}</span><span className="block text-[11px] text-text-3">{e.user.role}</span></span></span></td>
                  <td className="px-2 py-2"><Input type="number" min={0} max={30} step={0.5} className="w-20 h-8 num" value={draft[e.user_id] ?? e.days_off} onChange={(ev) => setDraft((d) => ({ ...d, [e.user_id]: Number(ev.target.value) }))} aria-label={`${e.user.name} days off`} /></td>
                  <td className="px-2 py-2 text-right"><span className="num">{n1(e.available_hours)}</span><span className="text-text-3 text-xs"> h</span><div className="mt-1 ml-auto w-20"><Progress value={e.available_hours} max={maxHours} height={3} /></div></td>
                  <td className="px-2 py-2 text-right num font-semibold">{n1(e.suggested_points)}<span className="text-text-3 text-xs font-normal">{unit}</span></td>
                  <td className="px-2 py-2"><span className="inline-flex items-center gap-2" title={tip}><div className="w-20"><Progress value={(p?.confidence ?? 0) * 100} color={(p?.confidence ?? 0) > 0.6 ? "var(--green)" : "var(--gold)"} height={4} /></div><span className="num text-xs text-text-3">{Math.round((p?.confidence ?? 0) * 100)}%</span></span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <footer className="px-4 py-3 flex flex-wrap items-center gap-3 border-t border-border bg-surface-2/40">
        <div className="flex-1 min-w-[200px]"><div className="flex justify-between text-xs mb-1"><span className="eyebrow">Team capacity</span><span className="num">{n1(teamTotal)}{unit} · {n1(cap.team_hours)} h</span></div><Progress value={100} color="var(--teal)" height={6} /></div>
        {dirty && <Button variant="secondary" loading={put.isPending} onClick={() => save()}>Save</Button>}
        <Button variant="primary" iconRight={ChevronRight} loading={put.isPending} onClick={() => (dirty ? save(onNext) : onNext())}>Pick work</Button>
      </footer>
    </section>
  );
}

/* ---------- ② pick work ---------- */
function PickStep({ sprint, project, plan, loading, error, refetch, picked, setPicked, onBack, onNext }: { sprint: Sprint; project: Project | undefined; plan: PlanSuggestion | undefined; loading: boolean; error: boolean; refetch: () => void; picked: Set<string>; setPicked: (s: Set<string>) => void; onBack: () => void; onNext: () => void }) {
  const setAgent = useUI((s) => s.setAgentOpen);
  const [open, setOpen] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const method = plan?.capacity.method ?? "points";
  const value = (i: WorkItem) => (method === "hours" ? i.estimate_hours ?? 0 : method === "throughput" ? 1 : i.points ?? 0);
  const capacity = plan ? (method === "hours" ? plan.capacity.team_hours : method === "throughput" ? plan.capacity.team_count : plan.capacity.team_points) : 0;
  const chosen = (plan?.candidates ?? []).filter((c) => picked.has(c.id));
  const total = chosen.reduce((a, c) => a + value(c), 0);
  const ratio = capacity > 0 ? total / capacity : 0;
  const gaugeColor = ratio > 1.05 ? "var(--rust)" : ratio > 0.9 ? "var(--gold)" : "var(--green)";
  const perPerson = useMemo(() => {
    const m = new Map<string, { user: WorkItem["assignee"]; v: number }>();
    chosen.forEach((c) => { const k = c.assignee_id ?? "unassigned"; const cur = m.get(k) ?? { user: c.assignee, v: 0 }; cur.v += value(c); m.set(k, cur); });
    return [...m.entries()];
  }, [chosen, method]); // eslint-disable-line react-hooks/exhaustive-deps
  const toggle = (id: string) => { const s = new Set(picked); if (s.has(id)) s.delete(id); else s.add(id); setPicked(s); };
  const list = (plan?.candidates ?? []).filter((c) => !q || c.title.toLowerCase().includes(q.toLowerCase()) || c.key.toLowerCase().includes(q.toLowerCase()));
  const unit = method === "hours" ? "h" : method === "throughput" ? "" : "pts";
  const askAgent = () => setAgent(true, { sprint_id: sprint.id, sprint_name: sprint.name, picked: [...picked] });

  if (loading) return <div className="space-y-2"><Skeleton className="h-12" /><LoadingRows n={6} /></div>;
  if (error || !plan) return <EmptyState icon="⚠️" title="No suggestions available" body="The planner couldn't rank the backlog." action={<Button icon={RefreshCw} onClick={refetch}>Try again</Button>} />;
  return (
    <section className="panel overflow-hidden animate-in">
      <header className="px-4 pt-4 pb-3 flex flex-wrap items-start justify-between gap-3">
        <div><div className="eyebrow">Step 2 of 3</div><h2 className="text-base">Fill the sprint</h2><p className="text-xs text-text-3 mt-0.5">Recommended items are pre-checked ({Math.round(plan.confidence * 100)}% confidence). {plan.notes[0] ?? ""}</p></div>
        <div className="flex items-center gap-2"><Button size="sm" variant="ghost" icon={RefreshCw} onClick={refetch}>Re-rank</Button><Button size="sm" variant="teal" icon={Sparkles} onClick={askAgent}>Ask the agent to review</Button></div>
      </header>
      <div className="px-4 pb-3 grid gap-3 md:grid-cols-[1fr_auto] items-end">
        <div>
          <div className="flex justify-between text-xs mb-1"><span className="eyebrow">Load vs capacity</span><span className="num" style={{ color: gaugeColor }}>{n1(total)} / {n1(capacity)} {unit} · {pct(total, capacity || 1)}%</span></div>
          <Progress value={total} max={capacity || 1} color={gaugeColor} height={8} />
          <div className="mt-2 flex flex-wrap gap-1.5">{perPerson.map(([k, v]) => <Badge key={k} size="xs" className="gap-1.5"><Avatar user={v.user} size={14} />{v.user?.name ?? "Unassigned"} · <span className="num">{n1(v.v)}</span></Badge>)}</div>
        </div>
        <Input placeholder="Filter candidates…" value={q} onChange={(e) => setQ(e.target.value)} className="h-8 w-48" />
      </div>
      {list.length === 0 ? <div className="p-4"><EmptyState icon="🧰" title="Nothing ready to pull" body="Groom the backlog: ready, unscheduled items appear here." /></div> : (
        <ul className="divide-y divide-border max-h-[52vh] overflow-y-auto">
          {list.map((c) => {
            const ty = typeOf(project, c.type); const on = picked.has(c.id), rec = plan.recommended_ids.includes(c.id);
            return (
              <li key={c.id} className={cn("flex items-start gap-3 px-4 py-2.5 hover:bg-surface-2/60", on && "bg-surface-2/40")}>
                <input type="checkbox" className="mt-1 accent-[var(--teal)]" checked={on} onChange={() => toggle(c.id)} aria-label={`Include ${c.key}`} />
                <button className="flex-1 min-w-0 text-left" onClick={() => setOpen(c.id)}>
                  <div className="flex items-center gap-2 text-sm"><span className="num text-xs text-text-3"><span style={{ color: ty?.color }}>{ty?.icon}</span> {c.key}</span><span className="truncate">{c.title}</span>{rec && <Badge size="xs" color="var(--teal)">recommended</Badge>}</div>
                  <div className="text-[11px] text-text-3 mt-0.5 truncate">{c.reason}</div>
                </button>
                <div className="text-right shrink-0 text-xs">
                  <div className="num font-semibold">{n1(value(c))}<span className="text-text-3 font-normal"> {unit}</span></div>
                  <div className="text-text-3" title="planner score"><span style={{ color: `var(--prio-${c.priority})` }}>{priorityIcon[c.priority]}</span> score <span className="num">{n1(c.score)}</span></div>
                </div>
                <Avatar user={c.assignee} size={22} />
              </li>
            );
          })}
        </ul>
      )}
      <footer className="px-4 py-3 flex items-center justify-between gap-3 border-t border-border bg-surface-2/40"><Button variant="ghost" onClick={onBack}>← Capacity</Button><span className="text-xs text-text-3">{picked.size} selected</span><Button variant="primary" iconRight={ChevronRight} disabled={picked.size === 0} onClick={onNext}>Review &amp; commit</Button></footer>
      <ItemDrawer itemId={open} onClose={() => setOpen(null)} />
    </section>
  );
}

/* ---------- ③ commit ---------- */
function CommitStep({ sprint, plan, picked, onBack, onStart }: { sprint: Sprint; plan: PlanSuggestion | undefined; picked: Set<string>; onBack: () => void; onStart: () => void }) {
  const commit = useCommitPlan(sprint.id);
  const [committed, setCommitted] = useState(false);
  const chosen = (plan?.candidates ?? []).filter((c) => picked.has(c.id));
  const pts = chosen.reduce((a, c) => a + (c.points ?? 0), 0);
  const go = () => commit.mutate([...picked], { onSuccess: () => { setCommitted(true); celebrate("small"); toast.fun("Grid is set", `${picked.size} items committed to ${sprint.name}.`); }, onError: (e) => toast.error("Couldn't commit the plan", (e as Error).message) });
  return (
    <section className="panel panel-cut p-5 animate-in">
      <div className="hairline mb-4" />
      <div className="eyebrow">Step 3 of 3</div>
      <h2 className="text-lg">Commit {sprint.name}</h2>
      <div className="grid grid-cols-3 gap-3 my-4">
        <div><div className="eyebrow">Items</div><div className="text-2xl font-display font-bold">{chosen.length}</div></div>
        <div><div className="eyebrow">Points</div><div className="text-2xl font-display font-bold">{pts}</div></div>
        <div><div className="eyebrow">Capacity</div><div className="text-2xl font-display font-bold">{n1(plan?.capacity.team_points ?? 0)}</div></div>
      </div>
      <ul className="text-sm space-y-1 max-h-48 overflow-y-auto mb-4">{chosen.map((c) => <li key={c.id} className="flex gap-2"><span className="num text-xs text-text-3 w-16 shrink-0">{c.key}</span><span className="truncate">{c.title}</span></li>)}</ul>
      {committed ? (
        <div className="flex flex-wrap items-center gap-3 p-3 rounded-[10px] border border-green/40 bg-green/10">
          <Check className="text-green" size={18} /><span className="text-sm flex-1">Committed. {sprint.state === "planned" ? "Ready when you are." : "Scope updated."}</span>
          {sprint.state === "planned" && <Button variant="primary" icon={Flag} onClick={onStart}>Start sprint</Button>}
        </div>
      ) : (
        <div className="flex items-center justify-between gap-3"><Button variant="ghost" onClick={onBack}>← Pick work</Button><Button variant="primary" icon={Check} loading={commit.isPending} disabled={chosen.length === 0} onClick={go}>Commit {chosen.length} items</Button></div>
      )}
    </section>
  );
}
