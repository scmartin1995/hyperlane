import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Badge, Button, IconButton, Input, Skeleton, toast } from "@/components/ui";
import { useLabelMutations, useLabels } from "./hooks";

export function LabelsManager({ pid }: { pid: string }) {
  const { data: labels, isLoading } = useLabels(pid);
  const m = useLabelMutations(pid);
  const [name, setName] = useState(""); const [color, setColor] = useState("#27cfc3");
  const add = () => { if (!name.trim()) return; m.create.mutate({ name: name.trim(), color }, { onSuccess: () => setName(""), onError: (e) => toast.error("Couldn't add label", (e as Error).message) }); };
  return (
    <section className="panel p-4">
      <div className="eyebrow">Labels</div><h2 className="text-base mb-3">Tags for items</h2>
      {isLoading ? <Skeleton className="h-16" /> : (
        <ul className="flex flex-wrap gap-1.5 mb-3">
          {labels?.length === 0 && <li className="text-xs text-text-3">No labels yet.</li>}
          {labels?.map((l) => (
            <li key={l.id} className="inline-flex items-center gap-1">
              <Badge color={l.color}>{l.name}</Badge>
              <input type="color" value={l.color} onChange={(e) => m.update.mutate({ id: l.id, color: e.target.value }, { onError: (er) => toast.error("Couldn't update", (er as Error).message) })} className="w-5 h-5 bg-transparent" aria-label={`Color for ${l.name}`} />
              <IconButton icon={Trash2} label={`Delete ${l.name}`} size="xs" onClick={() => { if (confirm(`Delete label "${l.name}"?`)) m.remove.mutate(l.id, { onError: (er) => toast.error("Couldn't delete", (er as Error).message) }); }} />
            </li>
          ))}
        </ul>
      )}
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); add(); }}><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="New label" className="h-8" /><input type="color" value={color} onChange={(e) => setColor(e.target.value)} className="h-8 w-9 bg-transparent" aria-label="Color" /><Button size="sm" type="submit" icon={Plus} loading={m.create.isPending}>Add</Button></form>
    </section>
  );
}
