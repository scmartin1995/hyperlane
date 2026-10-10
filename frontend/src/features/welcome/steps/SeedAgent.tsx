// "Build it with the agent": prompt → proposal tree with checkboxes → apply.
import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Sparkles, Check } from "lucide-react";
import { api } from "@/api/client";
import type { BacklogProposal, WorkItem } from "@/api/types";
import { Button, Textarea, cn, toast } from "@/components/ui";

type PItem = BacklogProposal["items"][number];

export function SeedAgent({ projectId, onDone }: { projectId: string; onDone: (created: WorkItem[]) => void }) {
  const qc = useQueryClient();
  const [prompt, setPrompt] = useState("");
  const [proposal, setProposal] = useState<BacklogProposal | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const gen = useMutation({
    mutationFn: () => api.post<BacklogProposal>(`/projects/${projectId}/backlog/generate`, { prompt: prompt.trim() }),
    onSuccess: (p) => { setProposal(p); setChecked(new Set(p.items.map((i) => i.temp_id))); if (!p.items.length) toast.info("The agent needs more to go on", p.questions.join("\n") || p.summary); },
    onError: (e) => toast.error("The agent couldn't draft a backlog", String(e)),
  });
  const apply = useMutation({
    mutationFn: () => {
      const keep = new Set(checked);
      // Keep parents of checked items so hierarchy survives.
      const byId = new Map(proposal!.items.map((i) => [i.temp_id, i]));
      for (const id of [...keep]) { let cur = byId.get(id); while (cur?.parent_temp_id) { keep.add(cur.parent_temp_id); cur = byId.get(cur.parent_temp_id); } }
      return api.post<WorkItem[]>(`/projects/${projectId}/backlog/apply`, { items: proposal!.items.filter((i) => keep.has(i.temp_id)) });
    },
    onSuccess: (created) => { qc.invalidateQueries({ queryKey: ["items"] }); toast.fun(`${created.length} items on the grid.`, "The agent drafted them; you own them now."); onDone(created); },
    onError: (e) => toast.error("Couldn't apply the proposal", String(e)),
  });
  const tree = useMemo(() => {
    if (!proposal) return [] as { item: PItem; depth: number }[];
    const kids = new Map<string | null, PItem[]>();
    proposal.items.forEach((i) => { const k = i.parent_temp_id ?? null; kids.set(k, [...(kids.get(k) ?? []), i]); });
    const out: { item: PItem; depth: number }[] = [];
    const walk = (p: string | null, d: number) => (kids.get(p) ?? []).forEach((i) => { out.push({ item: i, depth: d }); walk(i.temp_id, d + 1); });
    walk(null, 0);
    return out;
  }, [proposal]);
  const toggle = (id: string) => setChecked((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

  return (
    <div className="space-y-3 animate-in">
      {!proposal ? (
        <>
          <Textarea autoFocus value={prompt} onChange={(e) => setPrompt(e.target.value)} className="min-h-[140px]" placeholder={"Describe the product or the next big push. Who it's for, what it must do, what 'done' means. The agent drafts epics → features → stories with acceptance criteria and point guesses.\n\nCtrl+Enter to generate."}
            onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && prompt.trim()) gen.mutate(); }} />
          <div className="flex justify-end"><Button variant="teal" icon={Sparkles} loading={gen.isPending} disabled={prompt.trim().length < 10} onClick={() => gen.mutate()}>{gen.isPending ? "Drafting…" : "Draft the backlog"}</Button></div>
        </>
      ) : (
        <>
          {proposal.summary && <p className="text-sm text-text-2">{proposal.summary}</p>}
          {proposal.questions.length > 0 && <div className="panel p-3 text-xs"><div className="eyebrow mb-1">The agent would like to know</div><ul className="list-disc pl-4 space-y-0.5 text-text-2">{proposal.questions.map((q, i) => <li key={i}>{q}</li>)}</ul><p className="text-text-3 mt-1">You can answer later in the agent drawer; this draft is still usable.</p></div>}
          <div className="max-h-[320px] overflow-y-auto rounded-[8px] border border-border divide-y divide-border">
            {tree.map(({ item, depth }) => (
              <label key={item.temp_id} className={cn("flex items-start gap-2 px-2 py-1.5 text-sm cursor-pointer hover:bg-surface-2", !checked.has(item.temp_id) && "opacity-50")} style={{ paddingLeft: 8 + depth * 20 }}>
                <input type="checkbox" checked={checked.has(item.temp_id)} onChange={() => toggle(item.temp_id)} className="mt-1 accent-[var(--teal)]" />
                <span className="flex-1 min-w-0"><span className="font-display text-[10px] uppercase tracking-wider text-text-3 mr-1.5">{item.type}</span><span className="font-medium">{item.title}</span>{item.description && <span className="block text-xs text-text-3 line-clamp-1">{item.description}</span>}</span>
                {item.points != null && <span className="num text-[11px] text-text-3">{item.points}pt</span>}
              </label>
            ))}
            {!tree.length && <div className="p-4 text-sm text-text-3">No items proposed. Try a more detailed prompt.</div>}
          </div>
          <div className="flex items-center justify-between"><Button variant="ghost" size="sm" onClick={() => setProposal(null)}>Rewrite prompt</Button><span className="num text-xs text-text-3">{checked.size} of {proposal.items.length} selected</span><Button variant="primary" icon={Check} loading={apply.isPending} disabled={!checked.size} onClick={() => apply.mutate()}>Add {checked.size} items</Button></div>
        </>
      )}
    </div>
  );
}
