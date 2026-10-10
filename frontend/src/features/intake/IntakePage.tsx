// Request log (email connector threads). List at /intake, detail at /intake/:id.
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Mail, MessageSquare, Globe, Hash, Plus, AlertCircle } from "lucide-react";
import type { IntakeRequest } from "@/api/types";
import { useProjects } from "@/api/queries";
import { useUI, label } from "@/lib/store";
import { ago } from "@/lib/format";
import { Badge, Button, EmptyState, Input, Kbd, PageHeader, Skeleton, Tabs, cn } from "@/components/ui";
import { IntakeDetail } from "./IntakeDetail";
import { NewRequestModal } from "./NewRequestModal";
import { useIntakeList } from "./hooks";

export const STATE_COLOR: Record<IntakeRequest["state"], string> = { new: "var(--teal)", clarifying: "var(--gold)", ready: "var(--green)", converted: "var(--purple-light)", rejected: "var(--rust)", on_hold: "var(--smoke)" };
export const STATE_LABEL: Record<IntakeRequest["state"], string> = { new: "New", clarifying: "Clarifying", ready: "Ready", converted: "Converted", rejected: "Rejected", on_hold: "On hold" };
export function ChannelIcon({ channel, size = 14 }: { channel: string; size?: number }) {
  const c = channel.toLowerCase();
  if (c.includes("mail")) return <Mail size={size} aria-label="Email" />;
  if (c.includes("slack")) return <Hash size={size} aria-label="Slack" />;
  if (c.includes("teams")) return <MessageSquare size={size} aria-label="Teams" />;
  return <Globe size={size} aria-label={channel} />;
}

export default function IntakePage() {
  const { id } = useParams<{ id?: string }>();
  if (id) return <IntakeDetail id={id} />;
  return <Inbox />;
}

type F = "all" | IntakeRequest["state"];
function Inbox() {
  const flavor = useUI((s) => s.flavor);
  const [filter, setFilter] = useState<F>("all");
  const [q, setQ] = useState(""); const [showNew, setShowNew] = useState(false); const [cursor, setCursor] = useState(0);
  const { data, isLoading, isError } = useIntakeList();
  const { data: projects } = useProjects();
  const nav = useNavigate();
  const list = useMemo(() => (data ?? []).filter((r) => (filter === "all" || r.state === filter) && (!q || `${r.subject} ${r.requester_name ?? ""} ${r.summary ?? ""}`.toLowerCase().includes(q.toLowerCase()))).sort((a, b) => b.last_activity_at.localeCompare(a.last_activity_at)), [data, filter, q]);
  const counts = useMemo(() => { const c: Record<string, number> = { all: data?.length ?? 0 }; (data ?? []).forEach((r) => { c[r.state] = (c[r.state] ?? 0) + 1; }); return c; }, [data]);
  useEffect(() => { const k = (e: KeyboardEvent) => { const tag = (e.target as HTMLElement)?.tagName; if (tag === "INPUT" || tag === "TEXTAREA" || showNew) return; if (e.key === "n") { e.preventDefault(); setShowNew(true); } if (e.key === "j") setCursor((c) => Math.min(list.length - 1, c + 1)); if (e.key === "k") setCursor((c) => Math.max(0, c - 1)); if (e.key === "Enter" && list[cursor]) nav(`/intake/${list[cursor].id}`); }; window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k); }, [list, cursor, nav, showNew]);
  if (isError) return <EmptyState icon="⚠️" title="Couldn't load the inbox" />;
  const tabs = (["all", "new", "clarifying", "ready", "converted", "on_hold", "rejected"] as F[]).map((k) => ({ key: k, label: k === "all" ? "All" : STATE_LABEL[k], count: counts[k] ?? 0 }));
  return (
    <div>
      <PageHeader eyebrow="Intake · Requests" title={label("intake", flavor)} subtitle="Requests from email, Slack, Teams and the web. The assistant clarifies, drafts requirements, and you convert."
        actions={<><Input placeholder="Search requests…" value={q} onChange={(e) => setQ(e.target.value)} className="h-8 w-52" /><Kbd>n</Kbd><Button variant="primary" icon={Plus} onClick={() => setShowNew(true)}>New request</Button></>} />
      <Tabs className="mb-3 flex-wrap" value={filter} onChange={setFilter} tabs={tabs} />
      {isLoading ? <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-16" />)}</div> : list.length === 0 ? (
        <EmptyState icon="📨" title={filter === "all" ? "The inbox is quiet" : `Nothing ${STATE_LABEL[filter as IntakeRequest["state"]]?.toLowerCase()}`} body={filter === "all" ? "Requests arrive from email intake, Slack, Teams, or the form here." : "Switch filters to see other requests."} action={filter === "all" && <Button variant="primary" icon={Plus} onClick={() => setShowNew(true)}>Log a request</Button>} />
      ) : (
        <ul className="space-y-1.5">
          {list.map((r, i) => {
            const p = projects?.find((x) => x.id === r.project_id);
            return (
              <li key={r.id}><button onClick={() => nav(`/intake/${r.id}`)} className={cn("w-full text-left panel px-4 py-3 hover:border-gold transition-colors flex items-start gap-3 animate-in", i === cursor && "border-gold")}>
                <span className="mt-0.5 text-text-3"><ChannelIcon channel={r.channel} /></span>
                <span className="flex-1 min-w-0">
                  <span className="flex items-center gap-2"><span className="font-display font-semibold truncate">{r.subject}</span>{r.needs_human && <Badge size="xs" color="var(--rust)"><AlertCircle size={10} /> needs a human</Badge>}</span>
                  <span className="block text-xs text-text-3 truncate">{r.requester_name ?? r.requester_email ?? "Anonymous"} · {r.summary ?? r.original_body.slice(0, 120)}</span>
                </span>
                <span className="flex flex-col items-end gap-1 shrink-0"><Badge size="xs" color={STATE_COLOR[r.state]} dot>{STATE_LABEL[r.state]}</Badge><span className="text-[10px] text-text-3">{p ? `${p.key} · ` : ""}{ago(r.last_activity_at)}</span></span>
              </button></li>
            );
          })}
        </ul>
      )}
      <NewRequestModal open={showNew} onClose={() => setShowNew(false)} />
    </div>
  );
}
