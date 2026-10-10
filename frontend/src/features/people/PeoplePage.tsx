// Team · People. Grid at /people, detail at /people/:id.
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Plus, Slack, Clock } from "lucide-react";
import type { User } from "@/api/types";
import { useMe, useUsers } from "@/api/queries";
import { useUI, label } from "@/lib/store";
import { ago } from "@/lib/format";
import { Avatar, Badge, Button, EmptyState, Input, Kbd, PageHeader, Skeleton, cn } from "@/components/ui";
import { AddPersonModal } from "./AddPersonModal";
import { PersonDetail } from "./PersonDetail";

export default function PeoplePage() {
  const { id } = useParams<{ id?: string }>();
  if (id) return <PersonDetail userId={id} />;
  return <PeopleGrid />;
}

function PeopleGrid() {
  const flavor = useUI((s) => s.flavor);
  const { data: users, isLoading, isError } = useUsers();
  const { data: me } = useMe();
  const [q, setQ] = useState(""); const [showAdd, setShowAdd] = useState(false); const [inactive, setInactive] = useState(false);
  const nav = useNavigate();
  useEffect(() => { const k = (e: KeyboardEvent) => { const tag = (e.target as HTMLElement)?.tagName; if (tag === "INPUT" || tag === "TEXTAREA" || showAdd) return; if (e.key === "n") { e.preventDefault(); setShowAdd(true); } if (e.key === "/" ) { /* agent */ } }; window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k); }, [showAdd]);
  const list = (users ?? []).filter((u) => (inactive || u.is_active) && (!q || `${u.name} ${u.role} ${u.skills.join(" ")}`.toLowerCase().includes(q.toLowerCase())));
  if (isError) return <EmptyState icon="⚠️" title="Couldn't load people" />;
  return (
    <div>
      <PageHeader eyebrow="Team" title={label("people", flavor)} subtitle="Roles, skills, hours, and what the planner has learned about each person."
        actions={<><Input placeholder="Filter by name, role, skill…" value={q} onChange={(e) => setQ(e.target.value)} className="h-8 w-56" /><label className="text-xs text-text-3 inline-flex items-center gap-1"><input type="checkbox" checked={inactive} onChange={(e) => setInactive(e.target.checked)} /> show inactive</label><Kbd>n</Kbd><Button variant="primary" icon={Plus} onClick={() => setShowAdd(true)}>Add person</Button></>} />
      {isLoading ? <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-40" />)}</div>
        : list.length === 0 ? <EmptyState icon="👥" title={q ? "Nobody matches" : "No people yet"} body={q ? "Try a different filter." : "Add the people on the team. Each gets a profile and a private checklist."} action={!q && <Button variant="primary" icon={Plus} onClick={() => setShowAdd(true)}>Add person</Button>} />
        : <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{list.map((u) => <PersonCard key={u.id} user={u} isMe={me?.id === u.id} onOpen={() => nav(`/people/${u.id}`)} />)}</div>}
      <AddPersonModal open={showAdd} onClose={() => setShowAdd(false)} />
    </div>
  );
}

function PersonCard({ user: u, isMe, onOpen }: { user: User; isMe: boolean; onOpen: () => void }) {
  return (
    <Link to={`/people/${u.id}`} onClick={(e) => { e.preventDefault(); onOpen(); }} className={cn("panel panel-cut p-4 block hover:border-gold transition-colors animate-in no-underline text-text", !u.is_active && "opacity-60")}>
      <div className="flex items-start gap-3">
        <Avatar user={u} size={44} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2"><h3 className="font-display font-bold truncate">{u.name}</h3>{isMe && <Badge size="xs" color="var(--gold)">you</Badge>}{!u.is_active && <Badge size="xs">inactive</Badge>}</div>
          <div className="text-xs text-text-3 truncate">{u.role || "No role"} · @{u.handle}</div>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-1 min-h-[22px]">{u.skills.slice(0, 5).map((s) => <Badge key={s} size="xs">{s}</Badge>)}{u.skills.length > 5 && <Badge size="xs">+{u.skills.length - 5}</Badge>}</div>
      <div className="mt-3 flex items-center justify-between text-[11px] text-text-3">
        <span className="inline-flex items-center gap-1"><Clock size={11} /><span className="num">{u.hours_per_week}</span>h/wk · focus <span className="num">{Math.round(u.focus_factor * 100)}%</span></span>
        <span className="inline-flex items-center gap-2">{u.slack_user_id && <Slack size={11} className="text-teal" aria-label="Slack linked" />}<span>{u.last_seen_at ? `seen ${ago(u.last_seen_at)}` : "never seen"}</span></span>
      </div>
    </Link>
  );
}
