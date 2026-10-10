import { useEffect, useState } from "react";
import { Plus, Save, Trash2 } from "lucide-react";
import type { ItemType, Project } from "@/api/types";
import { Button, IconButton, Input, toast } from "@/components/ui";
import { useUpdateProject } from "./hooks";

const slug = (s: string) => s.toLowerCase().trim().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "type";

export function ItemTypesEditor({ project: p }: { project: Project }) {
  const update = useUpdateProject(p.id);
  const [rows, setRows] = useState<ItemType[]>([]);
  useEffect(() => setRows(p.item_types.map((t) => ({ ...t }))), [p.item_types]);
  const set = (i: number, patch: Partial<ItemType>) => setRows((r) => r.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const dirty = JSON.stringify(rows) !== JSON.stringify(p.item_types);
  const save = () => {
    if (new Set(rows.map((r) => r.key)).size !== rows.length) return toast.error("Type keys must be unique");
    update.mutate({ item_types: [...rows].sort((a, b) => a.level - b.level) }, { onSuccess: () => toast.success("Item types saved"), onError: (e) => toast.error("Couldn't save", (e as Error).message) });
  };
  return (
    <section className="panel p-4">
      <div className="flex items-center justify-between mb-3"><div><div className="eyebrow">Item types</div><h2 className="text-base">Hierarchy</h2></div><Button size="sm" variant="primary" icon={Save} loading={update.isPending} disabled={!dirty} onClick={save}>Save</Button></div>
      <div className="grid grid-cols-[44px_1fr_1fr_40px_56px_auto] gap-1.5 text-[10px] eyebrow mb-1"><span>Icon</span><span>Name</span><span>Plural</span><span>Color</span><span>Level</span><span /></div>
      <ul className="space-y-1.5">
        {rows.map((t, i) => (
          <li key={i} className="grid grid-cols-[44px_1fr_1fr_40px_56px_auto] gap-1.5 items-center">
            <Input className="h-8 text-center px-0" value={t.icon} onChange={(e) => set(i, { icon: e.target.value })} aria-label="Icon" />
            <div><Input className="h-8" value={t.name} onChange={(e) => set(i, { name: e.target.value, key: p.item_types.some((x) => x.key === t.key) ? t.key : slug(e.target.value) })} aria-label="Name" /><div className="text-[10px] text-text-3 num">{t.key}</div></div>
            <Input className="h-8" value={t.plural} onChange={(e) => set(i, { plural: e.target.value })} aria-label="Plural" />
            <input type="color" value={t.color || "#869791"} onChange={(e) => set(i, { color: e.target.value })} className="h-8 w-9 bg-transparent" aria-label="Color" />
            <Input type="number" min={0} max={9} className="h-8 num" value={t.level} onChange={(e) => set(i, { level: Number(e.target.value) })} aria-label="Level" title="0 = top (epic), higher = nested deeper" />
            <IconButton icon={Trash2} label="Delete type" size="xs" onClick={() => setRows((x) => x.filter((_, j) => j !== i))} />
          </li>
        ))}
      </ul>
      <Button size="sm" variant="ghost" icon={Plus} className="mt-2" onClick={() => setRows((x) => [...x, { key: `type_${x.length + 1}`, name: "New type", plural: "New types", icon: "▫️", color: "#869791", level: Math.max(0, ...x.map((t) => t.level)) }])}>Add type</Button>
      <p className="text-[11px] text-text-3 mt-2">Level 0 is the top of the tree (epics); items can only be parented under a lower level.</p>
    </section>
  );
}
