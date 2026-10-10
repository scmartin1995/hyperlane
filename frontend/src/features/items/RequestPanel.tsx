// Shown on items that came from a request (email connector / form): who asked, what the assistant
// understood, open questions, triage actions and a way to message the requester.
import { useState } from "react";
import { Mail, Globe, Hash, Sparkles, Check, Zap, X, Clock, Send } from "lucide-react";
import { addDays, format } from "date-fns";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { IntakeMeta, IntakeRequest, Project, WorkItem } from "@/api/types";
import { useMessageRequester, useTriageAction } from "@/api/queries";
import { Badge, Button, Menu, Panel, Textarea, toast, celebrate } from "@/components/ui";
import { useSprints } from "./hooks";
import { RequirementsCard } from "@/features/intake/RequirementsCard";

const CHANNEL_ICON: Record<string, typeof Mail> = { email: Mail, web: Globe, slack: Hash, chat: Sparkles };

export function RequestPanel({ item, project }: { item: WorkItem; project: Project | undefined }) {
  const meta = (item.custom?.intake ?? null) as IntakeMeta | null;
  const req = useQuery({ queryKey: ["intake", meta?.request_id], queryFn: () => api.get<IntakeRequest>(`/intake/${meta!.request_id}`), enabled: !!meta?.request_id });
  const act = useTriageAction();
  const msg = useMessageRequester();
  const { data: sprints } = useSprints(item.project_id);
  const [text, setText] = useState("");
  if (!meta) return null;
  const Icon = CHANNEL_ICON[meta.channel] ?? Globe;
  const active = sprints?.find((s) => s.state === "active");
  const open = ["new", "clarifying", "ready", "snoozed"].includes(meta.state);
  const conf = Math.round((meta.confidence ?? 0) * 100);
  const run = (action: "accept" | "escalate" | "decline" | "snooze", extra: Record<string, unknown> = {}) => act.mutate({ id: item.id, action, ...extra }, {
    onSuccess: (r) => { if (action === "accept") { celebrate("small"); toast.success("Accepted into the backlog", r.created.length ? `${r.created.length} proposed items created underneath.` : undefined); } else toast.info(`Request ${action}d`); },
    onError: (e) => toast.error("Couldn't triage", (e as Error).message),
  });
  return (
    <Panel tone="cream" className="p-4 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="w-8 h-8 rounded-full bg-rust text-cream inline-flex items-center justify-center shrink-0"><Icon size={14} /></span>
        <div className="flex-1 min-w-0">
          <div className="eyebrow">Request · {meta.channel}</div>
          <div className="text-sm">from <span className="font-semibold">{meta.requester_name ?? meta.requester_email ?? "unknown"}</span>{meta.requester_email && meta.requester_name && <span className="text-text-3"> · {meta.requester_email}</span>}</div>
        </div>
        {meta.needs_human ? <Badge color="var(--rust)" dot>needs a human</Badge>
          : meta.state === "accepted" ? <Badge color="var(--green)" dot>accepted</Badge>
          : meta.state === "declined" ? <Badge color="var(--smoke)" dot>declined</Badge>
          : meta.state === "snoozed" ? <Badge color="var(--smoke)" dot>snoozed until {meta.snoozed_until}</Badge>
          : meta.state === "ready" ? <Badge color="var(--green)" dot>ready to triage</Badge>
          : meta.state === "clarifying" ? <Badge color="var(--teal)" dot>assistant clarifying · {meta.questions_asked}/{meta.max_questions}</Badge>
          : <Badge color="var(--gold-deep)" dot>new · waiting for the assistant</Badge>}
      </div>
      <div className="flex items-center gap-2 text-[11px] text-text-3"><span>assistant confidence</span><span className="flex-1 h-1.5 rounded-full bg-surface-3 overflow-hidden max-w-[200px]"><span className="block h-full rounded-full" style={{ width: `${conf}%`, background: conf >= 75 ? "var(--green)" : conf >= 40 ? "var(--gold-deep)" : "var(--rust)" }} /></span><span className="num">{conf}%</span></div>
      {req.data?.requirements && Object.keys(req.data.requirements).length > 0 && <div className="panel p-3 bg-surface"><RequirementsCard req={req.data.requirements} /></div>}
      {open && (
        <div className="flex flex-wrap items-center gap-1.5">
          <Button size="sm" variant="primary" icon={Check} loading={act.isPending} onClick={() => run("accept")}>Accept</Button>
          <Button size="sm" variant="teal" icon={Zap} disabled={!active} title={active ? `Pull into ${active.name}` : "No active sprint"} onClick={() => run("escalate")}>Escalate to sprint</Button>
          <Menu trigger={<Button size="sm" variant="ghost" icon={Clock}>Snooze</Button>} align="left" items={[1, 3, 7, 14].map((d) => ({ label: `${d} day${d === 1 ? "" : "s"}`, onClick: () => run("snooze", { until: format(addDays(new Date(), d), "yyyy-MM-dd") }) }))} />
          <Button size="sm" variant="ghost" icon={X} className="text-rust" onClick={() => { const reason = prompt("Decline this request? Optional reason:") ?? undefined; if (reason !== undefined) run("decline", { reason }); }}>Decline</Button>
        </div>
      )}
      <form onSubmit={(e) => { e.preventDefault(); if (!text.trim()) return; msg.mutate({ id: item.id, body: text.trim() }, { onSuccess: () => { setText(""); toast.success(meta.channel === "email" ? "Sent to the requester" : "Added to the thread"); }, onError: (er) => toast.error("Couldn't send", (er as Error).message) }); }} className="flex gap-2 items-end">
        <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} placeholder={`Message ${meta.requester_name ?? "the requester"}… ${meta.channel === "email" ? "(goes out by email)" : ""}`} className="min-h-[56px] text-sm" onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") (e.currentTarget.form as HTMLFormElement).requestSubmit(); }} />
        <Button size="md" variant="secondary" icon={Send} type="submit" loading={msg.isPending} disabled={!text.trim()}>Send</Button>
      </form>
    </Panel>
  );
}
