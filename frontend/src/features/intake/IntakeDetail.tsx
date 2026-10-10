import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Ban, PauseCircle, PlayCircle, RefreshCw, Send, Sparkles, StickyNote, ArrowRightCircle } from "lucide-react";
import type { IntakeMessage } from "@/api/types";
import { useProjects, useUsers } from "@/api/queries";
import { ago, fmtDateTime } from "@/lib/format";
import { Badge, Button, EmptyState, Markdown, Select, Skeleton, Textarea, Tabs, toast, cn } from "@/components/ui";
import { ChannelIcon, STATE_COLOR, STATE_LABEL } from "./IntakePage";
import { RequirementsCard } from "./RequirementsCard";
import { ConvertModal } from "./ConvertModal";
import { useIntakeMutations, useIntakeOne } from "./hooks";

export function IntakeDetail({ id }: { id: string }) {
  const { data: r, isLoading, isError } = useIntakeOne(id);
  const m = useIntakeMutations(id);
  const { data: users } = useUsers(); const { data: projects } = useProjects();
  const [convert, setConvert] = useState(false);
  const [mode, setMode] = useState<"inbound" | "internal">("inbound"); const [body, setBody] = useState("");
  if (isLoading) return <div className="space-y-3"><Skeleton className="h-10 w-80" /><Skeleton className="h-64" /></div>;
  if (isError || !r) return <EmptyState icon="🛰️" title="Request not found" action={<Link to="/intake"><Button>Back to inbox</Button></Link>} />;
  const err = (w: string) => (e: unknown) => toast.error(`Couldn't ${w}`, (e as Error).message);
  const send = () => { if (!body.trim()) return; m.message.mutate({ body: body.trim(), direction: mode, author: mode === "inbound" ? r.requester_name ?? "Requester" : undefined }, { onSuccess: () => { setBody(""); toast.success(mode === "inbound" ? "Reply recorded" : "Note added"); }, onError: err("send") }); };
  const terminal = r.state === "converted" || r.state === "rejected";
  const isEmail = r.channel.toLowerCase().includes("mail");
  return (
    <div>
      <Link to="/intake" className="inline-flex items-center gap-1 text-xs text-text-3 hover:text-text no-underline"><ArrowLeft size={12} /> Inbox</Link>
      <div className="flex flex-wrap items-start justify-between gap-3 mt-1 mb-4">
        <div className="min-w-0"><div className="flex items-center gap-2"><h1 className="text-xl leading-tight truncate normal-case tracking-normal">{r.subject}</h1><Badge color={STATE_COLOR[r.state]} dot>{STATE_LABEL[r.state]}</Badge>{r.needs_human && <Badge color="var(--rust)">needs a human</Badge>}</div>
          <p className="text-text-3 text-sm mt-1 inline-flex items-center gap-1.5"><ChannelIcon channel={r.channel} size={12} /> {r.requester_name ?? "Anonymous"}{r.requester_email && <span>&lt;{r.requester_email}&gt;</span>} · {ago(r.created_at)} · {r.questions_asked}/{r.max_questions} questions asked</p></div>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="ghost" icon={RefreshCw} loading={m.analyze.isPending} onClick={() => m.analyze.mutate(undefined, { onSuccess: () => toast.success("Re-analyzed"), onError: err("analyze") })}>Analyze again</Button>
          {!terminal && (r.state === "on_hold" ? <Button size="sm" variant="ghost" icon={PlayCircle} onClick={() => m.patch.mutate({ state: "new" }, { onError: err("resume") })}>Resume</Button> : <Button size="sm" variant="ghost" icon={PauseCircle} onClick={() => m.patch.mutate({ state: "on_hold" }, { onError: err("hold") })}>Hold</Button>)}
          {!terminal && <Button size="sm" variant="ghost" icon={Ban} className="hover:text-rust-light" onClick={() => { const reason = prompt("Reason (optional)") ?? undefined; if (reason !== null) m.reject.mutate(reason, { onSuccess: () => toast.info("Request rejected"), onError: err("reject") }); }}>Reject</Button>}
          {!terminal && <Button size="sm" variant="primary" icon={ArrowRightCircle} onClick={() => setConvert(true)}>Convert to backlog</Button>}
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
        <div className="space-y-4">
          {r.summary && <section className="panel p-4"><div className="eyebrow inline-flex items-center gap-1"><Sparkles size={11} /> Agent summary</div><Markdown className="mt-1">{r.summary}</Markdown></section>}
          <RequirementsCard req={r.requirements} />
          <section className="panel p-4">
            <div className="eyebrow">Conversation</div><h2 className="text-base mb-3">Thread</h2>
            <div className="space-y-2">
              <Bubble msg={{ id: "orig", request_id: r.id, direction: "inbound", author: r.requester_name ?? "Requester", body: r.original_body, external_ref: null, meta: {}, created_at: r.created_at }} />
              {r.messages.map((msg) => <Bubble key={msg.id} msg={msg} />)}
            </div>
            {!terminal && (
              <div className="mt-4 border-t border-border pt-3">
                <Tabs className="mb-2" value={mode} onChange={setMode} tabs={[{ key: "inbound", label: isEmail ? "Log requester's reply" : "Reply as requester" }, { key: "internal", label: "Internal note" }]} />
                <Textarea value={body} onChange={(e) => setBody(e.target.value)} placeholder={mode === "inbound" ? "What the requester said (re-runs analysis)…" : "A note for the team; the requester never sees this."} className="min-h-[70px]" onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") send(); }} />
                <div className="flex justify-between items-center mt-2 text-[11px] text-text-3"><span>{isEmail && mode === "inbound" ? "Email replies arrive automatically; use this for replies that came another way." : "Ctrl+Enter sends."}</span><Button size="sm" variant={mode === "inbound" ? "teal" : "secondary"} icon={mode === "inbound" ? Send : StickyNote} loading={m.message.isPending} onClick={send}>{mode === "inbound" ? "Post reply" : "Add note"}</Button></div>
              </div>
            )}
          </section>
        </div>
        <div className="space-y-4">
          <section className="panel p-4 space-y-3">
            <div className="eyebrow">Routing</div>
            <label className="block"><span className="eyebrow block mb-1">Owner</span><Select value={r.owner_id ?? ""} onChange={(e) => m.patch.mutate({ owner_id: e.target.value || null }, { onError: err("set owner") })}><option value="">Unassigned</option>{users?.filter((u) => u.is_active).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</Select></label>
            <label className="block"><span className="eyebrow block mb-1">Project</span><Select value={r.project_id ?? ""} onChange={(e) => m.patch.mutate({ project_id: e.target.value || null }, { onError: err("set project") })}><option value="">Undecided</option>{projects?.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.key}</option>)}</Select></label>
            <label className="block"><span className="eyebrow block mb-1">Max clarifying questions</span><Select value={r.max_questions} onChange={(e) => m.patch.mutate({ max_questions: Number(e.target.value) }, { onError: err("update") })}>{[0, 1, 2, 3, 5].map((n) => <option key={n} value={n}>{n}</option>)}</Select></label>
          </section>
          {r.converted_item_ids.length > 0 && <section className="panel p-4"><div className="eyebrow">Converted</div><ul className="text-sm mt-1 space-y-1">{r.converted_item_ids.map((i) => <li key={i}><Link to={`/items/${i}`}>Work item {i.slice(0, 6)}… ↗</Link></li>)}</ul></section>}
          {(r.requirements.proposed_items?.length ?? 0) > 0 && !terminal && <section className="panel p-4"><div className="eyebrow">Proposed items</div><ul className="text-sm mt-1 space-y-1">{r.requirements.proposed_items!.map((p, i) => <li key={i} className="flex gap-2"><Badge size="xs">{p.type}</Badge><span className="truncate">{p.title}</span>{p.points != null && <span className="num text-xs text-text-3 ml-auto">{p.points}</span>}</li>)}</ul><Button size="sm" className="mt-2 w-full" variant="primary" onClick={() => setConvert(true)}>Review &amp; convert</Button></section>}
        </div>
      </div>
      <ConvertModal open={convert} onClose={() => setConvert(false)} req={r} />
    </div>
  );
}

function Bubble({ msg }: { msg: IntakeMessage }) {
  const out = msg.direction === "outbound", internal = msg.direction === "internal";
  return (
    <div className={cn("flex", out ? "justify-end" : "justify-start")}>
      <div className={cn("max-w-[85%] rounded-[12px] px-3 py-2 text-sm", out ? "bg-teal-deep/40 border border-teal/30" : internal ? "bg-gold/10 border border-dashed border-gold/40" : "bg-surface-2 border border-border")}>
        <div className="flex items-center gap-2 text-[10px] text-text-3 mb-1"><span className="font-display font-semibold">{out ? "✨ Agent" : internal ? "📝 Internal" : msg.author}</span><span>{fmtDateTime(msg.created_at)}</span></div>
        <Markdown>{msg.body}</Markdown>
      </div>
    </div>
  );
}
