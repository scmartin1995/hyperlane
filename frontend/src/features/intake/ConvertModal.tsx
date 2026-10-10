import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Trash2 } from "lucide-react";
import type { IntakeRequest } from "@/api/types";
import { useProject, useProjects } from "@/api/queries";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { WorkItem } from "@/api/types";
import { Button, Field, IconButton, Input, Modal, Select, celebrate, toast } from "@/components/ui";
import { useIntakeMutations } from "./hooks";

type Row = { type: string; title: string; description?: string; points?: number | null; acceptance_criteria?: string };

export function ConvertModal({ open, onClose, req }: { open: boolean; onClose: () => void; req: IntakeRequest }) {
  const { convert } = useIntakeMutations(req.id);
  const { data: projects } = useProjects();
  const [pid, setPid] = useState(req.project_id ?? ""); const [parent, setParent] = useState("");
  const { data: project } = useProject(pid || undefined);
  const parents = useQuery({ queryKey: ["items", pid, { for: "parents" }], queryFn: () => api.get<WorkItem[]>(`/projects/${pid}/items?include_done=false&limit=200`), enabled: open && !!pid });
  const [rows, setRows] = useState<Row[]>([]);
  const nav = useNavigate();
  useEffect(() => { if (open) { setPid(req.project_id ?? projects?.[0]?.id ?? ""); setRows((req.requirements.proposed_items ?? []).map((p) => ({ ...p })) || []); } }, [open, req, projects]);
  useEffect(() => { if (rows.length === 0 && open) setRows([{ type: project?.settings.default_type ?? "story", title: req.subject, description: req.summary ?? undefined }]); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [open, project]);
  const types = project?.item_types ?? [];
  const parentCandidates = (parents.data ?? []).filter((i) => (types.find((t) => t.key === i.type)?.level ?? 0) < Math.max(...types.map((t) => t.level), 1));
  const set = (i: number, p: Partial<Row>) => setRows((r) => r.map((x, j) => (j === i ? { ...x, ...p } : x)));
  const submit = () => {
    if (!pid) return toast.error("Pick a project");
    const items = rows.filter((r) => r.title.trim()); if (!items.length) return toast.error("Add at least one item");
    convert.mutate({ project_id: pid, parent_id: parent || null, items }, { onSuccess: (created) => { celebrate("small"); toast.fun(`${created.length} item${created.length === 1 ? "" : "s"} added to the backlog`); onClose(); if (created[0]) nav(`/backlog`); }, onError: (e) => toast.error("Couldn't convert", (e as Error).message) });
  };
  return (
    <Modal open={open} onClose={onClose} width={720} eyebrow="Convert" title="Convert to backlog items" footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={convert.isPending} onClick={submit}>Create {rows.filter((r) => r.title.trim()).length} items</Button></>}>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <Field label="Project" required><Select value={pid} onChange={(e) => { setPid(e.target.value); setParent(""); }}><option value="">Choose…</option>{projects?.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.key}</option>)}</Select></Field>
        <Field label="Parent (optional)"><Select value={parent} onChange={(e) => setParent(e.target.value)}><option value="">None (top level)</option>{parentCandidates.map((i) => <option key={i.id} value={i.id}>{i.key} · {i.title}</option>)}</Select></Field>
      </div>
      <div className="space-y-2">
        {rows.map((r, i) => (
          <div key={i} className="grid grid-cols-[120px_1fr_70px_auto] gap-2 items-start">
            <Select className="h-8 text-xs" value={r.type} onChange={(e) => set(i, { type: e.target.value })} aria-label="Type">{types.length ? types.map((t) => <option key={t.key} value={t.key}>{t.icon} {t.name}</option>) : <option value={r.type}>{r.type}</option>}</Select>
            <div><Input className="h-8" value={r.title} onChange={(e) => set(i, { title: e.target.value })} placeholder="Title" aria-label="Title" />{r.description && <p className="text-[11px] text-text-3 mt-0.5 line-clamp-2">{r.description}</p>}</div>
            <Input type="number" className="h-8 num" value={r.points ?? ""} onChange={(e) => set(i, { points: e.target.value === "" ? null : Number(e.target.value) })} placeholder="pts" aria-label="Points" />
            <IconButton icon={Trash2} label="Remove" onClick={() => setRows((x) => x.filter((_, j) => j !== i))} />
          </div>
        ))}
        <Button size="sm" variant="ghost" icon={Plus} onClick={() => setRows((x) => [...x, { type: project?.settings.default_type ?? "story", title: "" }])}>Add item</Button>
      </div>
    </Modal>
  );
}
