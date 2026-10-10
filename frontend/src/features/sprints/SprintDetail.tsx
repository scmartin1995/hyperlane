import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { differenceInCalendarDays, parseISO } from "date-fns";
import { ArrowLeft, Flag, FlagOff, Play, Trash2 } from "lucide-react";
import type { Sprint } from "@/api/types";
import { useProject, useSprint, useSprintList } from "@/api/queries";
import { fmtDate } from "@/lib/format";
import { Badge, Button, EmptyState, Field, Modal, Select, Skeleton, Tabs, celebrate, toast } from "@/components/ui";
import { SprintOverview } from "./SprintOverview";
import { SprintPlan } from "./SprintPlan";
import { SprintRetro } from "./SprintRetro";
import { useCloseSprint, useDeleteSprint, useStartSprint, type CloseResult } from "./hooks";

type Tab = "overview" | "plan" | "retro";
const STATE_COLOR: Record<Sprint["state"], string> = { active: "var(--teal)", planned: "var(--gold)", closed: "var(--green)" };

export function sprintDay(s: Sprint) {
  const days = Math.max(1, differenceInCalendarDays(parseISO(s.end_date), parseISO(s.start_date)) + 1);
  const day = Math.min(days, Math.max(0, differenceInCalendarDays(new Date(), parseISO(s.start_date)) + 1));
  return { day, days };
}

export function SprintDetail({ sprintId, tab, projectId }: { sprintId: string; tab: Tab; projectId: string }) {
  const nav = useNavigate();
  const { data: sprint, isLoading, isError } = useSprint(sprintId);
  const { data: project } = useProject(projectId);
  const [closing, setClosing] = useState(false);
  const [confirmStart, setConfirmStart] = useState(false);
  const start = useStartSprint(sprintId);
  const del = useDeleteSprint();

  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName; if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "1") nav(`/sprints/${sprintId}/overview`); if (e.key === "2") nav(`/sprints/${sprintId}/plan`); if (e.key === "3") nav(`/sprints/${sprintId}/retro`);
      if (e.key === "Escape") nav("/sprints");
    };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, [nav, sprintId]);

  if (isLoading) return <div className="space-y-3"><Skeleton className="h-8 w-64" /><Skeleton className="h-40 w-full" /></div>;
  if (isError || !sprint) return <EmptyState icon="🛰️" title="Sprint not found" body="It may have been deleted." action={<Link to="/sprints"><Button>Back to sprints</Button></Link>} />;
  const { day, days } = sprintDay(sprint);

  const doStart = () => start.mutate(undefined, {
    onSuccess: () => { setConfirmStart(false); celebrate("big"); toast.fun("Lights out — sprint started!", `${sprint.name} is live.`); nav(`/sprints/${sprintId}/overview`); },
    onError: (e) => toast.error("Couldn't start the sprint", (e as Error).message),
  });

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div className="min-w-0">
          <Link to="/sprints" className="inline-flex items-center gap-1 text-xs text-text-3 hover:text-text no-underline"><ArrowLeft size={12} /> All sprints</Link>
          <div className="flex items-center gap-2 mt-1">
            <h1 className="text-2xl leading-none truncate">{sprint.name}</h1>
            <Badge color={STATE_COLOR[sprint.state]} dot>{sprint.state}</Badge>
          </div>
          <p className="text-text-3 text-sm mt-1">{fmtDate(sprint.start_date, "MMM d")} → {fmtDate(sprint.end_date, "MMM d, yyyy")}
            {sprint.state === "active" && <> · day <span className="num text-text">{day}</span> of <span className="num">{days}</span></>}
            {sprint.state === "closed" && sprint.closed_at && <> · closed {fmtDate(sprint.closed_at)}</>}</p>
        </div>
        <div className="flex items-center gap-2">
          {sprint.state === "planned" && <Button variant="ghost" icon={Trash2} onClick={() => { if (confirm("Delete this planned sprint? Items go back to the backlog.")) del.mutate(sprintId, { onSuccess: () => { toast.info("Sprint deleted"); nav("/sprints"); }, onError: (e) => toast.error("Couldn't delete", (e as Error).message) }); }}>Delete</Button>}
          {sprint.state === "planned" && <Button variant="primary" icon={Play} onClick={() => setConfirmStart(true)}>Start sprint</Button>}
          {sprint.state === "active" && <Button variant="outline" icon={FlagOff} onClick={() => setClosing(true)}>Close sprint</Button>}
        </div>
      </div>
      <Tabs className="mb-4" value={tab} onChange={(t) => nav(`/sprints/${sprintId}/${t}`)} tabs={[{ key: "overview", label: "Overview" }, { key: "plan", label: "Plan" }, { key: "retro", label: "Retro" }]} />
      {tab === "overview" && <SprintOverview sprint={sprint} project={project} />}
      {tab === "plan" && <SprintPlan sprint={sprint} project={project} onStart={() => setConfirmStart(true)} />}
      {tab === "retro" && <SprintRetro sprint={sprint} project={project} />}

      <Modal open={confirmStart} onClose={() => setConfirmStart(false)} eyebrow="Lights out" title={`Start ${sprint.name}?`}
        footer={<><Button variant="ghost" onClick={() => setConfirmStart(false)}>Not yet</Button><Button variant="primary" icon={Flag} loading={start.isPending} onClick={doStart}>Start sprint</Button></>}>
        <p className="text-sm text-text-2">This snapshots the commitment ({sprint.committed_count || "the current"} items) so velocity and burndown measure against it. Only one sprint can be active at a time.</p>
      </Modal>
      <CloseSprintModal open={closing} onClose={() => setClosing(false)} sprint={sprint} projectId={projectId} />
    </div>
  );
}

function CloseSprintModal({ open, onClose, sprint, projectId }: { open: boolean; onClose: () => void; sprint: Sprint; projectId: string }) {
  const { data: sprints } = useSprintList(projectId, "planned");
  const close = useCloseSprint(sprint.id);
  const [carry, setCarry] = useState("next");
  const [result, setResult] = useState<CloseResult | null>(null);
  const nav = useNavigate();
  const unfinished = sprint.committed_count - sprint.completed_count;
  const submit = () => close.mutate(carry, {
    onSuccess: (r) => { setResult(r); celebrate("big"); toast.fun("Checkered flag!", `${r.completed.length} items crossed the line.`); },
    onError: (e) => toast.error("Couldn't close the sprint", (e as Error).message),
  });
  const finish = () => { setResult(null); onClose(); nav(`/sprints/${sprint.id}/retro`); };
  if (result) {
    const nextName = sprints?.find((s) => s.id === carry)?.name ?? (carry === "next" ? `Sprint ${sprint.number + 1}` : "the backlog");
    return (
      <Modal open={open} onClose={finish} eyebrow="Lap complete" title={`${sprint.name} closed`} footer={<><Button variant="ghost" onClick={() => { setResult(null); onClose(); }}>Done</Button><Button variant="primary" onClick={finish}>Run the retro →</Button></>}>
        <div className="text-center py-4">
          <div className="text-5xl mb-2">🏁</div>
          <div className="text-2xl font-display font-bold"><span className="num">{result.completed.length}</span> of <span className="num">{result.completed.length + result.carried.length}</span> done</div>
          <p className="text-text-2 mt-1">{result.carried.length === 0 ? "Clean sweep — nothing carried over." : `${result.carried.length} carried to ${nextName}.`}</p>
          <p className="text-text-3 text-xs mt-3">Velocity: <span className="num">{result.sprint.completed_points}</span> pts of <span className="num">{result.sprint.committed_points}</span> committed.</p>
        </div>
      </Modal>
    );
  }
  return (
    <Modal open={open} onClose={onClose} eyebrow="Checkered flag" title={`Close ${sprint.name}`} footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" icon={FlagOff} loading={close.isPending} onClick={submit}>Close sprint</Button></>}>
      <p className="text-sm text-text-2 mb-3">{unfinished > 0 ? <><span className="num text-text">{unfinished}</span> item{unfinished === 1 ? "" : "s"} {unfinished === 1 ? "isn't" : "aren't"} done yet. Where should they go?</> : "Everything's done. Closing records velocity and updates capacity profiles."}</p>
      <Field label="Carry unfinished work to">
        <Select value={carry} onChange={(e) => setCarry(e.target.value)}>
          <option value="next">Next sprint (created if needed)</option>
          <option value="backlog">Back to the backlog</option>
          {sprints?.filter((s) => s.id !== sprint.id).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </Select>
      </Field>
    </Modal>
  );
}
