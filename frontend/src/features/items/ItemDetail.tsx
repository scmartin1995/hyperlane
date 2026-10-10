// Reusable full work-item view. Used by ItemPage and by the board/backlog drawers (compact).
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, Copy, ExternalLink, Sparkles, Archive } from "lucide-react";
import type { WorkItemInput } from "@/api/types";
import { useMe, useProject } from "@/api/queries";
import { useUI } from "@/lib/store";
import { ago } from "@/lib/format";
import { Button, EmptyState, IconButton, Select, Skeleton, Tabs, celebrate, cn, toast } from "@/components/ui";
import { useDeleteItem, useHotkey, useItem, useUpdateItem } from "./hooks";
import { TypeIcon, isDone } from "./common";
import { ItemFields } from "./ItemFields";
import { MarkdownEditor } from "./MarkdownEditor";
import { ItemChildren } from "./ItemChildren";
import { ItemDiscussion } from "./ItemDiscussion";
import { ItemActivityTab, TransitionsTimeline } from "./ItemActivity";

type Tab = "discussion" | "activity" | "transitions";

export function ItemDetail({ id, compact, onOpenItem, onArchived }: { id: string; compact?: boolean; onOpenItem?: (id: string) => void; onArchived?: () => void }) {
  const q = useItem(id);
  const item = q.data;
  const { data: project } = useProject(item?.project_id);
  const { data: me } = useMe();
  const update = useUpdateItem();
  const del = useDeleteItem();
  const ui = useUI();
  const nav = useNavigate();
  const [tab, setTab] = useState<Tab>("discussion");
  const [descEditing, setDescEditing] = useState(false);
  const [copied, setCopied] = useState(false);
  useEffect(() => { setTab("discussion"); setDescEditing(false); }, [id]);
  useHotkey("e", () => setDescEditing(true), { enabled: !!item && !descEditing });

  const patch = (p: Partial<WorkItemInput>) => {
    if (!item) return;
    const wasDone = isDone(project, item.status);
    update.mutate({ id: item.id, patch: p }, { onSuccess: (res) => { if (p.status && !wasDone && isDone(project, res.status)) { celebrate("small"); toast.fun(`${res.key} crossed the line.`, "Nice work. On to the next one."); } } });
  };
  const open = (cid: string) => (onOpenItem ? onOpenItem(cid) : nav(`/items/${cid}`));
  const copyKey = async () => { try { await navigator.clipboard.writeText(item?.key ?? ""); setCopied(true); setTimeout(() => setCopied(false), 1200); } catch { toast.info(item?.key ?? ""); } };

  if (q.isLoading) return <div className="p-5 space-y-3"><Skeleton className="h-4 w-24" /><Skeleton className="h-8 w-3/4" /><Skeleton className="h-24" /><Skeleton className="h-40" /></div>;
  if (q.isError || !item) return <div className="p-5"><EmptyState icon="🛰️" title="Item not found" body="It may have been archived or lives in a different project." action={<Button onClick={() => nav("/backlog")}>Back to the backlog</Button>} /></div>;

  const done = isDone(project, item.status);
  return (
    <div className={cn("animate-in", compact ? "p-4 space-y-5" : "space-y-6")}>
      <header className="space-y-2">
        <div className="flex items-center gap-2 flex-wrap">
          <TypeIcon project={project} type={item.type} size="md" />
          <Select value={item.type} onChange={(e) => patch({ type: e.target.value })} className="h-7 !w-auto text-xs" aria-label="Type">{(project?.item_types ?? []).map((t) => <option key={t.key} value={t.key}>{t.name}</option>)}</Select>
          <button type="button" onClick={copyKey} className="num inline-flex items-center gap-1 text-sm text-gold font-semibold hover:underline" title="Copy key" aria-label={`Copy ${item.key}`}>{item.key}{copied ? <Check size={12} className="text-green" /> : <Copy size={12} className="opacity-60" />}</button>
          {item.parent && <button type="button" onClick={() => open(item.parent!.id)} className="text-xs text-text-3 hover:text-text truncate max-w-[240px]">↑ {item.parent.key} · {item.parent.title}</button>}
          <span className="flex-1" />
          {compact && <IconButton icon={ExternalLink} label="Open full page" onClick={() => nav(`/items/${item.id}`)} />}
          <Button size="sm" variant="outline" icon={Sparkles} onClick={() => ui.setAgentOpen(true, { item_id: item.id, item_key: item.key, project_id: item.project_id })}>Ask the assistant</Button>
          <IconButton icon={Archive} label="Archive item" onClick={() => { if (confirm(`Archive ${item.key}?`)) del.mutate({ id: item.id }, { onSuccess: () => { toast.success(`${item.key} archived`); onArchived ? onArchived() : nav(-1); } }); }} />
        </div>
        <InlineTitle value={item.title} onSave={(t) => patch({ title: t })} className={cn(compact ? "text-xl" : "text-2xl", done && "line-through opacity-70")} />
        <div className="text-[11px] text-text-3">Created {ago(item.created_at)} · updated {ago(item.updated_at)}{item.sprint && <> · in <span className="text-text-2">{item.sprint.name}</span></>}</div>
      </header>

      <ItemFields item={item} project={project} onPatch={patch} compact={compact} />

      <MarkdownEditor label="Description" value={item.description} placeholder="Describe the why and the what. Press e to edit." onSave={(v) => patch({ description: v || null })} editing={descEditing} onEditingChange={setDescEditing} />
      <MarkdownEditor label="Acceptance criteria" value={item.acceptance_criteria} placeholder="Given / when / then… What does done look like?" onSave={(v) => patch({ acceptance_criteria: v || null })} />

      {(item.children.length > 0 || (project?.item_types.find((t) => t.key === item.type)?.level ?? 99) < Math.max(...(project?.item_types.map((t) => t.level) ?? [0]))) && (
        <ItemChildren parent={item} project={project} children={item.children} onOpen={open} />
      )}

      <section>
        <Tabs<Tab> value={tab} onChange={setTab} className="mb-3" tabs={[{ key: "discussion", label: "Discussion", count: item.comments.length }, { key: "activity", label: "Activity" }, { key: "transitions", label: "Transitions" }]} />
        {tab === "discussion" && <ItemDiscussion itemId={item.id} comments={item.comments} me={me} />}
        {tab === "activity" && <ItemActivityTab itemId={item.id} />}
        {tab === "transitions" && <TransitionsTimeline itemId={item.id} project={project} />}
      </section>
    </div>
  );
}

function InlineTitle({ value, onSave, className }: { value: string; onSave: (v: string) => void; className?: string }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  useEffect(() => { if (!editing) setDraft(value); }, [value, editing]);
  const commit = () => { const t = draft.trim(); if (t && t !== value) onSave(t); else setDraft(value); setEditing(false); };
  if (editing) return <input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} onBlur={commit} aria-label="Title" onKeyDown={(e) => { if (e.key === "Enter") commit(); if (e.key === "Escape") { e.stopPropagation(); setDraft(value); setEditing(false); } }} className={cn("w-full bg-surface-2 border border-teal rounded-[8px] px-2 py-1 font-display font-bold leading-tight", className)} />;
  return <h1 onClick={() => setEditing(true)} title="Click to edit" className={cn("normal-case tracking-normal font-bold leading-tight cursor-text rounded-[8px] px-2 py-1 -mx-2 hover:bg-surface-2/60", className)}>{value}</h1>;
}
