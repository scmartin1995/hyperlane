// Requests from the email connector (or the form) land here, at the top of the backlog, until someone triages them.
import { useState } from "react";
import { Mail, Globe, Hash, Sparkles, Check, Zap, X, Clock, ChevronDown, ChevronUp, MessageCircle } from "lucide-react";
import { addDays, format } from "date-fns";
import type { Project, Sprint, TriageItem } from "@/api/types";
import { useTriage, useTriageAction } from "@/api/queries";
import { Badge, Button, Menu, Select, cn, toast, celebrate } from "@/components/ui";
import { ago } from "@/lib/format";

const CHANNEL_ICON: Record<string, typeof Mail> = { email: Mail, web: Globe, slack: Hash, chat: Sparkles };

function StateBadge({ t }: { t: TriageItem }) {
  const m = t.intake;
  if (m.needs_human) return <Badge color="var(--rust)" dot>needs a human</Badge>;
  if (m.state === "snoozed") return <Badge color="var(--smoke)" dot>snoozed until {m.snoozed_until}</Badge>;
  if (m.state === "ready") return <Badge color="var(--green)" dot>ready to triage</Badge>;
  if (m.state === "clarifying") return <Badge color="var(--teal)" dot>assistant clarifying · {m.questions_asked}/{m.max_questions}</Badge>;
  return <Badge color="var(--gold-deep)" dot>new</Badge>;
}

export function TriagePanel({ project, sprints, onOpen }: { project: Project | undefined; sprints: Sprint[]; onOpen: (id: string) => void }) {
  const { data, isLoading } = useTriage(project?.id);
  const act = useTriageAction();
  const [collapsed, setCollapsed] = useState(false);
  const [types, setTypes] = useState<Record<string, string>>({});
  const items = data ?? [];
  const active = sprints.find((s) => s.state === "active");
  if (isLoading || items.length === 0) return null;

  const run = (t: TriageItem, action: "accept" | "escalate" | "decline" | "snooze", extra: Record<string, unknown> = {}) =>
    act.mutate({ id: t.id, action, type: types[t.id], ...extra }, {
      onSuccess: (r) => {
        if (action === "accept") { toast.success(`${t.key} added to the backlog`, r.created.length ? `${r.created.length} proposed items created underneath.` : undefined); celebrate("small"); }
        if (action === "escalate") toast.fun(`${t.key} pulled into ${active?.name ?? "the sprint"}`);
        if (action === "decline") toast.info(`${t.key} declined`, "The requester keeps the thread; the item is archived.");
        if (action === "snooze") toast.info(`${t.key} snoozed`);
      },
      onError: (e) => toast.error("Couldn't triage", (e as Error).message),
    });

  return (
    <section className="panel tone tone-cream p-4 mb-4">
      <header className="flex items-center gap-3">
        <span className="w-9 h-9 rounded-full bg-rust text-cream inline-flex items-center justify-center shrink-0"><Mail size={16} /></span>
        <div className="flex-1 min-w-0">
          <div className="eyebrow">Needs triage</div>
          <h2 className="text-base leading-tight">{items.length} request{items.length === 1 ? "" : "s"} waiting for a decision</h2>
        </div>
        <span className="text-[11px] text-text-3 hidden md:inline">Requests arrive from your email connector; the assistant clarifies them before they reach you.</span>
        <button onClick={() => setCollapsed((c) => !c)} className="h-8 w-8 inline-flex items-center justify-center rounded-full hover:bg-surface/60" aria-label="Toggle">{collapsed ? <ChevronDown size={16} /> : <ChevronUp size={16} />}</button>
      </header>
      {!collapsed && (
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          {items.map((t) => {
            const Icon = CHANNEL_ICON[t.intake.channel] ?? Globe;
            const conf = Math.round((t.intake.confidence ?? 0) * 100);
            const leafTypes = (project?.item_types ?? []).filter((x) => x.level > 0);
            return (
              <article key={t.id} className="panel p-4 flex flex-col gap-2.5 bg-surface">
                <div className="flex items-start gap-2">
                  <Icon size={15} className="text-text-3 mt-0.5 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <button onClick={() => onOpen(t.id)} className="text-left font-display font-bold text-[15px] leading-tight hover:text-purple">{t.title}</button>
                    <div className="text-[11px] text-text-3 mt-0.5">{t.intake.requester_name ?? t.intake.requester_email ?? "unknown requester"} · {ago(t.intake.last_activity_at ?? t.updated_at)} · <span className="num">{t.key}</span></div>
                  </div>
                  <StateBadge t={t} />
                </div>
                {t.intake.summary && <p className="text-sm text-text-2 line-clamp-3">{t.intake.summary}</p>}
                <div className="flex items-center gap-2 text-[11px] text-text-3">
                  <span>confidence</span>
                  <span className="flex-1 h-1.5 rounded-full bg-surface-3 overflow-hidden max-w-[160px]"><span className="block h-full rounded-full" style={{ width: `${conf}%`, background: conf >= 75 ? "var(--green)" : conf >= 40 ? "var(--gold-deep)" : "var(--rust)" }} /></span>
                  <span className="num">{conf}%</span>
                  {t.intake.proposed_count > 0 && <span>· {t.intake.proposed_count} proposed item{t.intake.proposed_count === 1 ? "" : "s"}</span>}
                  {t.intake.open_questions.length > 0 && <span>· {t.intake.open_questions.length} open question{t.intake.open_questions.length === 1 ? "" : "s"}</span>}
                </div>
                <div className="flex flex-wrap items-center gap-1.5 pt-1 border-t border-border">
                  <Select value={types[t.id] ?? t.type} onChange={(e) => setTypes({ ...types, [t.id]: e.target.value })} className="h-7 !w-auto text-xs" aria-label="Accept as type">{leafTypes.map((x) => <option key={x.key} value={x.key}>{x.icon} {x.name}</option>)}</Select>
                  <Button size="sm" variant="primary" icon={Check} loading={act.isPending && act.variables?.id === t.id} onClick={() => run(t, "accept")}>Accept</Button>
                  <Button size="sm" variant="teal" icon={Zap} disabled={!active} title={active ? `Pull into ${active.name}` : "No active sprint"} onClick={() => run(t, "escalate")}>Escalate</Button>
                  <Button size="sm" variant="ghost" icon={MessageCircle} onClick={() => onOpen(t.id)}>Discuss</Button>
                  <span className="flex-1" />
                  <Menu align="right" trigger={<Button size="sm" variant="ghost" icon={Clock}>Snooze</Button>} items={[1, 3, 7, 14].map((d) => ({ label: `${d} day${d === 1 ? "" : "s"} (${format(addDays(new Date(), d), "MMM d")})`, onClick: () => run(t, "snooze", { until: format(addDays(new Date(), d), "yyyy-MM-dd") }) }))} />
                  <Button size="sm" variant="ghost" icon={X} className={cn("text-rust")} onClick={() => { const reason = prompt("Decline this request? Optional reason:") ?? undefined; if (reason !== undefined) run(t, "decline", { reason }); }}>Decline</Button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
