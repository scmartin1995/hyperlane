import { useEffect, useState } from "react";
import { ArrowDown, ArrowUp, Plus, Save, Trash2 } from "lucide-react";
import type { Project, StatusCategory, WorkflowState } from "@/api/types";
import { Button, IconButton, Input, Select, toast, cn } from "@/components/ui";
import { useUpdateProject } from "./hooks";

const slug = (s: string) => s.toLowerCase().trim().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "state";
type Row = WorkflowState & { _orig?: string };

export function WorkflowEditor({ project: p }: { project: Project }) {
  const update = useUpdateProject(p.id);
  const [rows, setRows] = useState<Row[]>([]);
  useEffect(() => setRows(p.workflow.map((s) => ({ ...s, _orig: s.key }))), [p.workflow]);
  const set = (i: number, patch: Partial<Row>) => setRows((r) => r.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const move = (i: number, d: -1 | 1) => setRows((r) => { const n = [...r]; const j = i + d; if (j < 0 || j >= n.length) return r; [n[i], n[j]] = [n[j], n[i]]; return n; });
  const dirty = JSON.stringify(rows.map(({ _orig, ...s }) => s)) !== JSON.stringify(p.workflow);
  const save = () => {
    const keys = rows.map((r) => r.key); if (new Set(keys).size !== keys.length) return toast.error("State keys must be unique");
    if (!rows.some((r) => r.category === "todo") || !rows.some((r) => r.category === "done")) return toast.error("Need at least one To do and one Done state");
    const workflow_rename: Record<string, string> = {}; rows.forEach((r) => { if (r._orig && r._orig !== r.key) workflow_rename[r._orig] = r.key; });
    const removed = p.workflow.filter((s) => !rows.some((r) => r._orig === s.key));
    if (removed.length && !confirm(`Delete ${removed.map((s) => s.name).join(", ")}? Items in those states will be moved to the first state of the same category.`)) return;
    update.mutate({ workflow: rows.map(({ _orig, ...s }) => s), workflow_rename }, { onSuccess: () => toast.success("Workflow saved"), onError: (e) => toast.error("Couldn't save workflow", (e as Error).message) });
  };
  return (
    <section className="panel p-4">
      <div className="flex items-center justify-between mb-3"><div><div className="eyebrow">Workflow</div><h2 className="text-base">Board columns</h2></div><Button size="sm" variant="primary" icon={Save} loading={update.isPending} disabled={!dirty} onClick={save}>Save</Button></div>
      <ul className="space-y-1.5">
        {rows.map((r, i) => (
          <li key={i} className="grid grid-cols-[auto_1fr_110px_64px_40px_auto] gap-1.5 items-center">
            <div className="flex flex-col"><IconButton icon={ArrowUp} label="Move up" size="xs" disabled={i === 0} onClick={() => move(i, -1)} /><IconButton icon={ArrowDown} label="Move down" size="xs" disabled={i === rows.length - 1} onClick={() => move(i, 1)} /></div>
            <div><Input className="h-8" value={r.name} onChange={(e) => set(i, { name: e.target.value, key: r._orig ? r.key : slug(e.target.value) })} aria-label="State name" /><div className="text-[10px] text-text-3 num mt-0.5">key: <input value={r.key} onChange={(e) => set(i, { key: slug(e.target.value) })} className="bg-transparent border-b border-transparent hover:border-border focus:border-teal outline-none w-28" aria-label="State key" /></div></div>
            <Select className="h-8 text-xs" value={r.category} onChange={(e) => set(i, { category: e.target.value as StatusCategory })} aria-label="Category"><option value="todo">To do</option><option value="in_progress">In progress</option><option value="done">Done</option></Select>
            <Input type="number" min={0} className={cn("h-8 num text-xs")} value={r.wip_limit ?? ""} placeholder="WIP" onChange={(e) => set(i, { wip_limit: e.target.value === "" ? null : Number(e.target.value) })} aria-label="WIP limit" />
            <input type="color" value={r.color || "#869791"} onChange={(e) => set(i, { color: e.target.value })} className="h-8 w-9 bg-transparent" aria-label="Color" />
            <IconButton icon={Trash2} label="Delete state" size="xs" onClick={() => setRows((x) => x.filter((_, j) => j !== i))} />
          </li>
        ))}
      </ul>
      <Button size="sm" variant="ghost" icon={Plus} className="mt-2" onClick={() => setRows((x) => [...x, { key: `state_${x.length + 1}`, name: "New state", category: "in_progress", wip_limit: null, color: "#27cfc3" }])}>Add state</Button>
      <p className="text-[11px] text-text-3 mt-2">Renaming a key migrates every item in that state. Order here is the board order.</p>
    </section>
  );
}
