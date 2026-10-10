// Retro: three columns + mood + stats + agent summary + actions → private action items on close.
import { useState } from "react";
import { Lock, Plus, Sparkles, ThumbsUp } from "lucide-react";
import type { Project, Retro, RetroEntry, Sprint } from "@/api/types";
import { useMe, useUsers } from "@/api/queries";
import { Avatar, Badge, Button, EmptyState, Input, Markdown, Select, Skeleton, celebrate, toast, cn } from "@/components/ui";
import { useRetro, useRetroMutations } from "./hooks";

const COLS: { key: "went_well" | "improve" | "kudos"; title: string; sub: string; color: string; icon: string }[] = [
  { key: "went_well", title: "Went well", sub: "Keep doing", color: "var(--green)", icon: "🟢" },
  { key: "improve", title: "Improve", sub: "Fix next lap", color: "var(--gold)", icon: "🔧" },
  { key: "kudos", title: "Kudos", sub: "Shout-outs", color: "var(--purple-light)", icon: "🏆" },
];
const MOODS = ["😩", "😕", "😐", "🙂", "🤩"];

export function SprintRetro({ sprint, project }: { sprint: Sprint; project: Project | undefined }) {
  const { data: retro, isLoading, isError } = useRetro(sprint.id);
  const { data: me } = useMe();
  const { data: users } = useUsers();
  const m = useRetroMutations(sprint.id);
  const [actionText, setActionText] = useState("");
  void project;
  if (isLoading) return <div className="grid gap-3 md:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-48" />)}</div>;
  if (isError || !retro) return <EmptyState icon="⚠️" title="Retro unavailable" body="Couldn't load the retro for this sprint." />;
  const closed = retro.state === "closed";
  const myMood = me ? retro.mood[me.id] : undefined;
  const moodValues = Object.values(retro.mood);
  const avgMood = moodValues.length ? moodValues.reduce((a, b) => a + b, 0) / moodValues.length : null;
  const stats = Object.entries(retro.stats ?? {}).filter(([, v]) => typeof v === "number" || typeof v === "string").slice(0, 8);
  const closeRetro = () => { if (!confirm(`Close the retro? ${retro.actions.filter((a) => a.owner_id).length} actions become private checklist items for their owners.`)) return; m.close.mutate(undefined, { onSuccess: () => { celebrate("big"); toast.fun("Retro closed", "Actions landed in everyone's checklist."); }, onError: (e) => toast.error("Couldn't close the retro", (e as Error).message) }); };
  const err = (what: string) => (e: unknown) => toast.error(`Couldn't ${what}`, (e as Error).message);

  return (
    <div className="space-y-4">
      {/* stats strip + mood */}
      <div className="panel p-3 flex flex-wrap items-center gap-x-6 gap-y-2">
        <div className="flex items-center gap-2"><span className="eyebrow">Mood</span>
          {MOODS.map((emo, i) => <button key={i} disabled={closed} onClick={() => m.mood.mutate(i + 1, { onError: err("save mood") })} className={cn("text-xl leading-none px-1 rounded transition-transform hover:scale-125", myMood === i + 1 && "scale-125 drop-shadow-[0_0_6px_var(--gold)]", closed && "opacity-60")} aria-label={`Mood ${i + 1} of 5`} aria-pressed={myMood === i + 1}>{emo}</button>)}
          {avgMood != null && <span className="text-xs text-text-3 ml-1">team avg <span className="num text-text">{avgMood.toFixed(1)}</span> ({moodValues.length})</span>}
        </div>
        <div className="flex-1" />
        {stats.length === 0 ? <span className="text-xs text-text-3">Stats appear once the sprint has activity.</span> : stats.map(([k, v]) => <span key={k} className="text-xs text-text-3">{k.replace(/_/g, " ")} <span className="num text-text">{typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(1)) : String(v)}</span></span>)}
        {closed && <Badge color="var(--green)" dot><Lock size={10} /> closed</Badge>}
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        {COLS.map((c) => <Column key={c.key} col={c} entries={retro[c.key]} closed={closed} meId={me?.id} onAdd={(text) => m.addEntry.mutate({ column: c.key, text }, { onError: err("add note") })} onVote={(id) => m.vote.mutate({ column: c.key, entry_id: id }, { onError: err("vote") })} />)}
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <section className="panel p-4">
          <div className="flex items-center justify-between mb-2"><div><div className="eyebrow">Summary</div><h2 className="text-base">What the agent saw</h2></div>
            {!closed && <Button size="sm" variant="teal" icon={Sparkles} loading={m.generate.isPending} onClick={() => m.generate.mutate(undefined, { onError: err("generate the summary") })}>{retro.agent_summary ? "Regenerate" : "Generate summary"}</Button>}</div>
          {retro.agent_summary ? <Markdown>{retro.agent_summary}</Markdown> : <p className="text-sm text-text-3">Add a few notes, then generate a summary that pulls in the sprint stats.</p>}
        </section>
        <section className="panel p-4">
          <div className="eyebrow">Actions</div><h2 className="text-base mb-2">What we'll do about it</h2>
          <ul className="space-y-2 mb-3">
            {retro.actions.length === 0 && <li className="text-sm text-text-3">No actions yet. Each one becomes a private checklist item for its owner when the retro closes.</li>}
            {retro.actions.map((a) => (
              <li key={a.id} className="flex items-center gap-2 text-sm">
                <span className={cn("flex-1", a.done && "line-through text-text-3")}>{a.text}</span>
                {closed ? <Avatar user={users?.find((u) => u.id === a.owner_id) ?? null} size={22} /> : (
                  <Select className="h-7 !w-36 text-xs" value={a.owner_id ?? ""} onChange={(e) => m.update.mutate({ actions: retro.actions.map((x) => (x.id === a.id ? { ...x, owner_id: e.target.value || null } : x)) }, { onError: err("set owner") })} aria-label="Owner">
                    <option value="">Owner…</option>{users?.filter((u) => u.is_active).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                  </Select>
                )}
                {a.action_item_id && <Badge size="xs" color="var(--green)">in checklist</Badge>}
              </li>
            ))}
          </ul>
          {!closed && (
            <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (!actionText.trim()) return; m.addEntry.mutate({ column: "actions", text: actionText.trim(), owner_id: me?.id ?? null }, { onSuccess: () => setActionText(""), onError: err("add action") }); }}>
              <Input value={actionText} onChange={(e) => setActionText(e.target.value)} placeholder="Add an action… (Enter)" className="h-8" /><Button size="sm" type="submit" icon={Plus}>Add</Button>
            </form>
          )}
        </section>
      </div>

      {!closed && <div className="flex justify-end"><Button variant="primary" icon={Lock} loading={m.close.isPending} onClick={closeRetro}>Close retro</Button></div>}
    </div>
  );
}

function Column({ col, entries, closed, meId, onAdd, onVote }: { col: (typeof COLS)[number]; entries: RetroEntry[]; closed: boolean; meId?: string; onAdd: (t: string) => void; onVote: (id: string) => void }) {
  const [text, setText] = useState("");
  void meId;
  return (
    <section className="panel p-3 flex flex-col animate-in" style={{ borderTopColor: col.color, borderTopWidth: 2 }}>
      <div className="flex items-center justify-between mb-2"><div><div className="eyebrow">{col.sub}</div><h3 className="font-display font-bold">{col.icon} {col.title}</h3></div><span className="num text-xs text-text-3">{entries.length}</span></div>
      <ul className="space-y-1.5 flex-1">
        {entries.length === 0 && <li className="text-xs text-text-3 italic">Nothing here yet.</li>}
        {[...entries].sort((a, b) => b.votes - a.votes).map((e) => (
          <li key={e.id} className="flex items-start gap-2 text-sm bg-surface-2/60 rounded-[8px] px-2.5 py-2">
            <span className="flex-1">{e.text}</span>
            <button disabled={closed} onClick={() => onVote(e.id)} className="inline-flex items-center gap-1 text-xs text-text-3 hover:text-gold disabled:opacity-60" aria-label="Vote"><ThumbsUp size={12} /><span className="num">{e.votes}</span></button>
          </li>
        ))}
      </ul>
      {!closed && <form className="mt-2 flex gap-1" onSubmit={(ev) => { ev.preventDefault(); if (text.trim()) { onAdd(text.trim()); setText(""); } }}><Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Add a note…" className="h-8 text-xs" /><Button size="sm" type="submit" variant="ghost" icon={Plus} aria-label="Add" /></form>}
    </section>
  );
}
