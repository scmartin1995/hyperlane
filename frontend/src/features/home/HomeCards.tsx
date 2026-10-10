import { useState } from "react";
import { Sparkles } from "lucide-react";
// Home cards: active sprint, your lane, action items, intake, activity feed.
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckSquare, Inbox, CalendarRange } from "lucide-react";
import { api } from "@/api/client";
import type { IntakeRequest, MeOverview, Project, Sprint, WorkItem } from "@/api/types";
import { useProjectActivity } from "@/api/queries";
import { differenceInCalendarDays, parseISO } from "date-fns";
import { fmtDate, pct } from "@/lib/format";
import { useUI, label } from "@/lib/store";
import { Button, Panel, Progress, Skeleton, cn } from "@/components/ui";
import { useItems } from "@/features/items/hooks";
import { PointsChip, StatusBadge, TypeIcon, isDone, sumPoints } from "@/features/items/common";
import { ActivityList } from "@/features/items/ItemActivity";

export function ActiveSprintCard({ sprint, project }: { sprint: Sprint | undefined; project: Project | undefined }) {
  const ui = useUI();
  const items = useItems(sprint ? project?.id : undefined, { sprint_id: sprint?.id, include_done: true });
  if (!sprint) return (
    <Panel cut eyebrow={label("sprints", ui.flavor)} title="No active sprint">
      <p className="text-sm text-text-3">Plan a sprint to get a goal, a burndown and a forecast.</p>
      <Link to="/sprints" className="no-underline"><Button variant="primary" size="sm" className="mt-3" icon={CalendarRange}>Plan a sprint</Button></Link>
    </Panel>
  );
  const total = differenceInCalendarDays(parseISO(sprint.end_date), parseISO(sprint.start_date)) + 1;
  const day = Math.min(total, Math.max(0, differenceInCalendarDays(new Date(), parseISO(sprint.start_date)) + 1));
  const list = items.data ?? [];
  const done = list.filter((i) => isDone(project, i.status));
  const usePoints = project?.settings.estimation !== "throughput";
  const committed = usePoints ? sumPoints(list) : list.length; const finished = usePoints ? sumPoints(done) : done.length;
  const timePct = pct(day, total); const scopePct = pct(finished, committed);
  return (
    <Panel cut eyebrow={`${label("sprints", ui.flavor)} · active`} title={sprint.name} actions={<Link to="/board" className="no-underline"><Button size="sm" variant="teal" iconRight={ArrowRight}>Open board</Button></Link>}>
      {sprint.goal ? <p className="text-sm text-text-2 italic">“{sprint.goal}”</p> : <p className="text-sm text-text-3">No goal set. <Link to={`/sprints/${sprint.id}`}>Add one</Link> so the team knows what winning looks like.</p>}
      <div className="mt-3 flex items-center justify-between text-xs"><span className="font-display font-semibold">Day <span className="num">{day}</span> of <span className="num">{total}</span></span><span className="text-text-3 num">{fmtDate(sprint.start_date)} → {fmtDate(sprint.end_date)}</span></div>
      <Progress value={day} max={total} color="var(--gold)" className="mt-1" />
      <div className="mt-3 flex items-center justify-between text-xs"><span className="font-display font-semibold">Done <span className="num">{finished}</span> of <span className="num">{committed}</span>{usePoints ? " pts" : " items"}</span><span className={cn("num", scopePct >= timePct ? "text-green" : "text-rust-light")}>{scopePct}% {scopePct >= timePct ? "· on pace" : "· behind pace"}</span></div>
      <Progress value={finished} max={committed} color="var(--green)" className="mt-1" />
    </Panel>
  );
}

export function YourLane({ overview, loading, project, meId }: { overview: MeOverview | undefined; loading: boolean; project: Project | undefined; meId: string | undefined }) {
  const ui = useUI();
  const nav = useNavigate();
  // Fallback when /me/overview isn't ready: my assigned items from the project.
  const fallback = useItems(!overview && !loading && meId ? project?.id : undefined, { assignee_id: meId, include_done: false });
  const rows: WorkItem[] = overview ? dedupe([...overview.in_progress, ...overview.assigned]) : (fallback.data ?? []);
  return (
    <Panel eyebrow={ui.flavor ? "Your lane" : "Assigned to you"} title={ui.flavor ? "Your lane" : "Your work"} actions={<Link to="/board" className="text-xs">Board →</Link>}>
      {loading ? <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-8" />)}</div>
        : rows.length === 0 ? <p className="text-sm text-text-3">Nothing assigned to you. Grab something from the <Link to="/backlog">backlog</Link> or pull a card on the board.</p>
        : <ul className="divide-y divide-border -mx-1">{rows.slice(0, 8).map((i) => (
          <li key={i.id}><button type="button" onClick={() => nav(`/items/${i.id}`)} className="w-full flex items-center gap-2 px-1 h-9 text-sm text-left hover:bg-surface-2 rounded-[6px]">
            <TypeIcon project={project} type={i.type} /><span className="num text-[11px] text-text-3">{i.key}</span><span className="flex-1 truncate">{i.title}</span>{i.blocked && <span className="text-[10px] text-rust-light font-display">blocked</span>}<PointsChip points={i.points} /><StatusBadge project={project} status={i.status} />
          </button></li>))}</ul>}
    </Panel>
  );
}
const dedupe = (xs: WorkItem[]) => { const seen = new Set<string>(); return xs.filter((x) => (seen.has(x.id) ? false : (seen.add(x.id), true))); };

export function ActionItemsCard({ overview }: { overview: MeOverview | undefined }) {
  const ui = useUI();
  const open = overview?.action_items_open ?? 0; const od = overview?.action_items_overdue ?? 0;
  return (
    <Link to="/action-items" className="block no-underline text-text">
      <Panel className="flex items-center gap-4 hover:border-purple transition-colors">
        <span className="num font-display text-[30px] font-extrabold leading-none text-purple w-9 text-center">{open}</span>
        <div className="flex-1 min-w-0"><div className="font-semibold">{label("actionItems", ui.flavor)}</div><div className="text-[13px] text-text-3">{od > 0 ? <span className="text-rust">{od} overdue</span> : "Private to you"}</div></div>
        <ArrowRight size={16} className="text-text-3 shrink-0" />
      </Panel>
    </Link>
  );
}

export function IntakeCard() {
  const ui = useUI();
  const q = useQuery({ queryKey: ["triage", ui.projectId ?? ""], queryFn: () => api.get<WorkItem[]>(`/projects/${ui.projectId}/triage`), enabled: !!ui.projectId, retry: false });
  const n = q.data?.length ?? 0;
  return (
    <Link to="/backlog" className="block no-underline">
      <Panel tone={n > 0 ? "rust" : undefined} className="flex items-center gap-4 hover:brightness-105 transition">
        <span className={cn("num font-display text-[30px] font-extrabold leading-none w-9 text-center", n === 0 && "text-text-3")}>{n}</span>
        <div className="flex-1 min-w-0"><div className="font-semibold">{n === 1 ? "Request needs triage" : "Requests need triage"}</div><div className={cn("text-[13px]", n > 0 ? "text-cream/80" : "text-text-3")}>From your email connector</div></div>
        <ArrowRight size={16} className="opacity-70 shrink-0" />
      </Panel>
    </Link>
  );
}

export function ActivityFeed({ pid }: { pid: string | undefined }) {
  const q = useProjectActivity(pid, 20);
  return <Panel title="Recent activity"><ActivityList rows={q.data} loading={q.isLoading} emptyText="Quiet so far. Create or move something and it shows up here." /></Panel>;
}

export function Greeting({ name, emoji }: { name: string | undefined; emoji: string | undefined; flavor?: boolean }) {
  const ui = useUI();
  const [q, setQ] = useState("");
  const h = new Date().getHours();
  const tod = h < 5 ? "Working late" : h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
  const ask = (text: string) => { if (!text.trim()) return; ui.setAgentOpen(true, { prefill: text, nonce: Date.now() }); setQ(""); };
  const chips = ["How is the sprint tracking?", "What should we pull into next sprint?", "Draft stories for a new feature", "Summarize this week"];
  return (
    <div className="panel tone tone-purple !rounded-[20px] p-8 overflow-hidden relative w-full">
      <div className="eyebrow">Home</div>
      <h1 className="text-[28px] md:text-[32px] leading-none mt-1 text-cream">{tod}, {name?.split(" ")[0] ?? "there"} <span className="inline-block animate-float">{emoji ?? "✨"}</span></h1>
      <p className="text-cream/80 text-sm mt-2">Here's where things stand. Ask me anything about the project.</p>
      <form onSubmit={(e) => { e.preventDefault(); ask(q); }} className="mt-4 flex items-center gap-2 h-12 pl-4 pr-1.5 rounded-full bg-cream text-coal shadow-lg max-w-[720px]">
        <Sparkles size={16} className="text-purple shrink-0" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask the assistant…" className="flex-1 bg-transparent outline-none text-[15px] placeholder:text-smoke" />
        <button type="submit" className="h-9 px-4 rounded-full bg-purple text-cream font-display font-semibold text-sm hover:brightness-110">Ask</button>
      </form>
      <div className="mt-3 flex flex-wrap gap-1.5">{chips.map((c) => <button key={c} onClick={() => ask(c)} className="text-xs px-3 h-7 rounded-full bg-cream/15 text-cream hover:bg-cream/25 border border-cream/20 transition-colors">{c}</button>)}</div>
    </div>
  );
}
