import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { addDays, format, parseISO } from "date-fns";
import { Plus, Flag } from "lucide-react";
import type { Sprint } from "@/api/types";
import { useProject, useSprintList } from "@/api/queries";
import { useUI, label } from "@/lib/store";
import { fmtDate, pct } from "@/lib/format";
import { Badge, Button, EmptyState, Field, Input, Kbd, Modal, Progress, PageHeader, Textarea, toast, cn } from "@/components/ui";
import { LoadingRows } from "./common";
import { useCreateSprint } from "./hooks";

const STATE_COLOR: Record<Sprint["state"], string> = { active: "var(--teal)", planned: "var(--gold)", closed: "var(--green)" };
const STATE_ORDER: Record<Sprint["state"], number> = { active: 0, planned: 1, closed: 2 };

export function SprintList({ projectId }: { projectId: string }) {
  const flavor = useUI((s) => s.flavor);
  const { data: sprints, isLoading, isError } = useSprintList(projectId);
  const { data: project } = useProject(projectId);
  const [showNew, setShowNew] = useState(false);
  const nav = useNavigate();
  const sorted = useMemo(() => [...(sprints ?? [])].sort((a, b) => STATE_ORDER[a.state] - STATE_ORDER[b.state] || (a.state === "closed" ? b.number - a.number : a.number - b.number)), [sprints]);
  const [cursor, setCursor] = useState(0);

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || showNew) return;
      if (e.key === "n") { e.preventDefault(); setShowNew(true); }
      if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); setCursor((c) => Math.min(sorted.length - 1, c + 1)); }
      if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); setCursor((c) => Math.max(0, c - 1)); }
      if (e.key === "Enter" && sorted[cursor]) nav(`/sprints/${sorted[cursor].id}`);
    };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, [sorted, cursor, nav, showNew]);

  if (isError) return <EmptyState icon="⚠️" title="Couldn't load sprints" body="The server didn't answer. Try again in a moment." />;
  return (
    <div>
      <PageHeader eyebrow="Sprints" title={label("sprints", flavor)} subtitle="Plan it, run it, learn from it. The assistant learns your team's capacity as you go."
        actions={<><span className="hidden md:inline-flex items-center gap-1 text-xs text-text-3"><Kbd>j</Kbd><Kbd>k</Kbd> move · <Kbd>n</Kbd> new</span><Button variant="primary" icon={Plus} onClick={() => setShowNew(true)}>New sprint</Button></>} />
      {isLoading ? <LoadingRows n={3} /> : sorted.length === 0 ? (
        <EmptyState icon="🗓️" title="No sprints yet" body="Create the first sprint. Dates default to your project's sprint length." action={<Button variant="primary" icon={Plus} onClick={() => setShowNew(true)}>New sprint</Button>} />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {sorted.map((s, i) => <SprintCard key={s.id} sprint={s} focused={i === cursor} />)}
        </div>
      )}
      <NewSprintModal open={showNew} onClose={() => setShowNew(false)} projectId={projectId} sprints={sprints ?? []} sprintLength={project?.settings.sprint_length_days ?? 14} />
    </div>
  );
}

function SprintCard({ sprint: s, focused }: { sprint: Sprint; focused: boolean }) {
  const useCount = s.committed_points === 0 && s.committed_count > 0;
  const total = useCount ? s.committed_count : s.committed_points, done = useCount ? s.completed_count : s.completed_points;
  const today = new Date(), start = parseISO(s.start_date), end = parseISO(s.end_date);
  const days = Math.max(1, Math.round((end.getTime() - start.getTime()) / 86400000) + 1);
  const day = Math.min(days, Math.max(0, Math.round((today.getTime() - start.getTime()) / 86400000) + 1));
  return (
    <Link to={`/sprints/${s.id}`} className={cn("panel panel-cut p-4 block hover:border-gold transition-colors animate-in", focused && "border-gold glow-gold", s.state === "active" && "scanlines")}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="eyebrow">Sprint {s.number} · {fmtDate(s.start_date)} → {fmtDate(s.end_date)}</div>
          <h3 className="font-display font-bold text-lg truncate">{s.name}</h3>
        </div>
        <Badge color={STATE_COLOR[s.state]} dot>{s.state}</Badge>
      </div>
      <p className="text-sm text-text-2 mt-1 line-clamp-2 min-h-[2.5rem]">{s.goal || <span className="text-text-3 italic">No goal set yet.</span>}</p>
      <div className="mt-3 flex items-center justify-between text-xs text-text-3">
        <span><span className="num text-text">{done}</span> / <span className="num">{total}</span> {useCount ? "items" : "pts"} done</span>
        {s.state === "active" && <span>day <span className="num text-text">{day}</span> of <span className="num">{days}</span></span>}
        {s.state === "planned" && <span className="inline-flex items-center gap-1"><Flag size={11} /> {s.committed_count} items planned</span>}
      </div>
      <Progress className="mt-2" value={done} max={total || 1} color={s.state === "closed" ? "var(--green)" : "var(--teal)"} />
    </Link>
  );
}

export function NewSprintModal({ open, onClose, projectId, sprints, sprintLength }: { open: boolean; onClose: () => void; projectId: string; sprints: Sprint[]; sprintLength: number }) {
  const create = useCreateSprint(projectId);
  const nav = useNavigate();
  const nextNumber = sprints.length ? Math.max(...sprints.map((s) => s.number)) + 1 : 1;
  const lastEnd = sprints.length ? sprints.reduce((m, s) => (s.end_date > m ? s.end_date : m), sprints[0].end_date) : null;
  const defStart = lastEnd && parseISO(lastEnd) > new Date() ? addDays(parseISO(lastEnd), 1) : new Date();
  const [name, setName] = useState(""); const [goal, setGoal] = useState("");
  const [start, setStart] = useState(format(defStart, "yyyy-MM-dd")); const [end, setEnd] = useState(format(addDays(defStart, sprintLength - 1), "yyyy-MM-dd"));
  useEffect(() => { if (open) { setName(`Sprint ${nextNumber}`); setGoal(""); setStart(format(defStart, "yyyy-MM-dd")); setEnd(format(addDays(defStart, sprintLength - 1), "yyyy-MM-dd")); } /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [open]);
  const submit = () => create.mutate({ name: name.trim() || undefined, goal: goal.trim() || undefined, start_date: start, end_date: end }, {
    onSuccess: (s) => { toast.success(`${s.name} created`, "Head to Plan to fill it."); onClose(); nav(`/sprints/${s.id}/plan`); },
    onError: (e) => toast.error("Couldn't create the sprint", String((e as Error).message)),
  });
  return (
    <Modal open={open} onClose={onClose} eyebrow="New" title="New sprint" footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={create.isPending} onClick={submit}>Create sprint</Button></>}>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <Field label="Name" required><Input autoFocus value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Goal" hint="One sentence the team can rally around."><Textarea value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="Ship the onboarding flow end to end." onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") submit(); }} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Start"><Input type="date" value={start} onChange={(e) => { setStart(e.target.value); if (e.target.value) setEnd(format(addDays(parseISO(e.target.value), sprintLength - 1), "yyyy-MM-dd")); }} /></Field>
          <Field label="End" hint={`${sprintLength}-day sprints (change in Settings → Project)`}><Input type="date" value={end} min={start} onChange={(e) => setEnd(e.target.value)} /></Field>
        </div>
        <button type="submit" className="hidden" />
      </form>
    </Modal>
  );
}
