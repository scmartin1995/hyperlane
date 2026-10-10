// Comments with avatars, markdown, decisions pinned at the top, source badges, edit/delete own, Ctrl+Enter composer.
import { useMemo, useState } from "react";
import { Pin, PinOff, Pencil, Trash2, MessageSquare } from "lucide-react";
import type { Comment, User } from "@/api/types";
import { ago } from "@/lib/format";
import { Avatar, Badge, Button, IconButton, Markdown, Textarea, cn } from "@/components/ui";
import { useAddComment, useDeleteComment, useUpdateComment } from "./hooks";

const SOURCE_COLOR: Record<string, string> = { slack: "var(--purple-light)", email: "var(--teal)", agent: "var(--gold)", teams: "var(--teal-deep)" };

export function ItemDiscussion({ itemId, comments, me }: { itemId: string; comments: Comment[]; me: User | null | undefined }) {
  const add = useAddComment();
  const [body, setBody] = useState("");
  const [decision, setDecision] = useState(false);
  const sorted = useMemo(() => {
    const byTime = (a: Comment, b: Comment) => a.created_at.localeCompare(b.created_at);
    return [...comments.filter((c) => c.is_decision).sort(byTime), ...comments.filter((c) => !c.is_decision).sort(byTime)];
  }, [comments]);
  const submit = () => { const b = body.trim(); if (!b) return; add.mutate({ item_id: itemId, body: b, is_decision: decision }); setBody(""); setDecision(false); };
  return (
    <div className="space-y-3">
      {sorted.length === 0 && <div className="text-sm text-text-3 flex items-center gap-2 py-3"><MessageSquare size={15} /> No discussion yet. Decisions you pin here stay at the top.</div>}
      {sorted.map((c) => <CommentRow key={c.id} c={c} itemId={itemId} mine={!!me && c.author_id === me.id} />)}
      <div className="pt-2 border-t border-border">
        <div className="flex gap-2.5">
          <Avatar user={me ?? null} size={28} className="mt-1" />
          <div className="flex-1 space-y-2">
            <Textarea value={body} onChange={(e) => setBody(e.target.value)} placeholder="Add to the discussion… (markdown ok)" className="min-h-[64px]" aria-label="New comment"
              onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); submit(); } }} />
            <div className="flex items-center gap-2">
              <label className="inline-flex items-center gap-1.5 text-xs text-text-2 cursor-pointer"><input type="checkbox" checked={decision} onChange={(e) => setDecision(e.target.checked)} className="accent-[var(--gold)]" /> Mark as decision 📌</label>
              <span className="flex-1" />
              <span className="text-[11px] text-text-3">Ctrl+Enter</span>
              <Button size="sm" variant="primary" onClick={submit} disabled={!body.trim()} loading={add.isPending}>Comment</Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function CommentRow({ c, itemId, mine }: { c: Comment; itemId: string; mine: boolean }) {
  const update = useUpdateComment();
  const del = useDeleteComment();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(c.body);
  const save = () => { if (draft.trim() && draft !== c.body) update.mutate({ id: c.id, item_id: itemId, patch: { body: draft } }); setEditing(false); };
  const temp = c.id.startsWith("tmp-");
  return (
    <article className={cn("group flex gap-2.5 animate-in", c.is_decision && "panel p-3 border-gold/50 bg-gold/5", temp && "opacity-60")}>
      <Avatar user={c.author} size={28} className="mt-0.5" title={c.author_name ?? undefined} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap text-xs">
          <span className="font-display font-semibold text-text">{c.author?.name ?? c.author_name ?? "Someone"}</span>
          {c.is_decision && <Badge size="xs" color="var(--gold)">📌 Decision</Badge>}
          {c.source && c.source !== "web" && <Badge size="xs" color={SOURCE_COLOR[c.source]}>{c.source}</Badge>}
          <span className="text-text-3" title={c.created_at}>{ago(c.created_at)}{c.edited_at && " · edited"}</span>
          <span className="flex-1" />
          <span className="inline-flex opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
            <IconButton size="xs" icon={c.is_decision ? PinOff : Pin} label={c.is_decision ? "Unmark decision" : "Mark as decision"} disabled={temp} onClick={() => update.mutate({ id: c.id, item_id: itemId, patch: { is_decision: !c.is_decision } })} />
            {mine && <IconButton size="xs" icon={Pencil} label="Edit comment" disabled={temp} onClick={() => { setDraft(c.body); setEditing(true); }} />}
            {mine && <IconButton size="xs" icon={Trash2} label="Delete comment" disabled={temp} onClick={() => { if (confirm("Delete this comment?")) del.mutate({ id: c.id, item_id: itemId }); }} />}
          </span>
        </div>
        {editing ? (
          <div className="mt-1 space-y-1.5">
            <Textarea autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} className="min-h-[60px]" onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); save(); } if (e.key === "Escape") { e.stopPropagation(); setEditing(false); } }} />
            <div className="flex gap-1.5"><Button size="xs" variant="primary" onClick={save}>Save</Button><Button size="xs" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button></div>
          </div>
        ) : <Markdown className="mt-0.5">{c.body}</Markdown>}
      </div>
    </article>
  );
}
