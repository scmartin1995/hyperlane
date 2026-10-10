// Create a work item. Enter in the title or Ctrl+Enter anywhere submits. "Create another" keeps the modal open.
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Priority, WorkItem, WorkItemInput } from "@/api/types";
import { useProject, useUsers } from "@/api/queries";
import { Button, Field, Input, Modal, Select, Textarea, cn, toast } from "@/components/ui";
import { useCreateItem, useSprints } from "./hooks";
import { PRIORITIES, TypeIcon } from "./common";
import { LabelPicker, ParentPicker } from "./pickers";

export function CreateItemModal({ open, onClose, projectId, defaults, onCreated }: {
  open: boolean; onClose: () => void; projectId: string | undefined; defaults?: Partial<WorkItemInput>; onCreated?: (item: WorkItem) => void;
}) {
  const { data: project } = useProject(projectId);
  const { data: users } = useUsers();
  const { data: sprints } = useSprints(projectId);
  const create = useCreateItem(projectId);
  const nav = useNavigate();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [type, setType] = useState<string>("");
  const [parentId, setParentId] = useState<string | null>(null);
  const [points, setPoints] = useState<number | null>(null);
  const [priority, setPriority] = useState<Priority>("medium");
  const [assignee, setAssignee] = useState<string>("");
  const [sprint, setSprint] = useState<string>("");
  const [labels, setLabels] = useState<string[]>([]);
  const [another, setAnother] = useState(false);
  const scale = project?.settings.points_scale ?? [1, 2, 3, 5, 8, 13];

  // Reset only when the modal opens (callers pass inline `defaults` objects; re-running on every render would wipe typing).
  useEffect(() => {
    if (!open) return;
    setTitle(defaults?.title ?? ""); setDescription(defaults?.description ?? "");
    setType(defaults?.type ?? project?.settings.default_type ?? "");
    setParentId(defaults?.parent_id ?? null); setPoints(defaults?.points ?? null); setPriority(defaults?.priority ?? "medium");
    setAssignee(defaults?.assignee_id ?? ""); setSprint(defaults?.sprint_id ?? ""); setLabels(defaults?.labels ?? []);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (open && !type && project) setType(project.settings.default_type || project.item_types[project.item_types.length - 1]?.key || ""); }, [open, type, project]);

  const submit = () => {
    const t = title.trim(); if (!t || !projectId) return;
    const input: WorkItemInput = { title: t, type: type || undefined, parent_id: parentId, description: description || null, points, priority, assignee_id: assignee || null, sprint_id: sprint || null, labels, status: defaults?.status };
    create.mutate(input, {
      onSuccess: (item) => {
        toast.success(`${item.key} created`, item.title);
        onCreated?.(item);
        if (another) { setTitle(""); setDescription(""); setTimeout(() => (document.getElementById("create-item-title") as HTMLInputElement | null)?.focus(), 0); }
        else onClose();
      },
    });
  };
  const keys = (e: React.KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); submit(); } };

  return (
    <Modal open={open} onClose={onClose} eyebrow={project ? `${project.icon} ${project.name}` : "New item"} title="New work item" width={640}
      footer={<>
        <label className="mr-auto inline-flex items-center gap-1.5 text-xs text-text-2 cursor-pointer"><input type="checkbox" checked={another} onChange={(e) => setAnother(e.target.checked)} className="accent-[var(--gold)]" /> Create another</label>
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant="primary" onClick={submit} disabled={!title.trim()} loading={create.isPending}>Create <span className="opacity-60 text-[10px] ml-1">Ctrl+↵</span></Button>
      </>}>
      <div className="space-y-3" onKeyDown={keys}>
        <Field label="Title" required>
          <Input id="create-item-title" autoFocus value={title} onChange={(e) => setTitle(e.target.value)} placeholder="What needs to happen?" onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); submit(); } }} />
        </Field>
        <Field label="Type">
          <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Type">
            {(project?.item_types ?? []).map((t) => <button type="button" key={t.key} role="radio" aria-checked={type === t.key} onClick={() => setType(t.key)} className={cn("inline-flex items-center gap-1.5 h-8 px-2.5 rounded-[7px] border text-xs font-display font-semibold", type === t.key ? "border-gold text-gold bg-gold/10" : "border-border text-text-2 hover:border-border-strong")}><TypeIcon project={project} type={t.key} />{t.name}</button>)}
          </div>
        </Field>
        <Field label="Parent"><ParentPicker project={project} value={parentId} onChange={setParentId} placeholder="No parent (top level)" /></Field>
        <div className="grid grid-cols-2 gap-3">
          {project?.settings.estimation !== "hours" && <Field label="Points">
            <div className="flex flex-wrap gap-1" role="radiogroup" aria-label="Points">
              {scale.map((p) => <button type="button" key={p} role="radio" aria-checked={points === p} onClick={() => setPoints(points === p ? null : p)} className={cn("num h-8 min-w-8 px-2 rounded-[7px] border text-xs font-semibold", points === p ? "border-teal text-teal bg-teal/10" : "border-border text-text-2 hover:border-border-strong")}>{p}</button>)}
            </div>
          </Field>}
          <Field label="Priority"><Select value={priority} onChange={(e) => setPriority(e.target.value as Priority)}>{PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}</Select></Field>
          <Field label="Assignee"><Select value={assignee} onChange={(e) => setAssignee(e.target.value)}><option value="">Unassigned</option>{(users ?? []).filter((u) => u.is_active).map((u) => <option key={u.id} value={u.id}>{u.emoji} {u.name}</option>)}</Select></Field>
          <Field label="Sprint"><Select value={sprint} onChange={(e) => setSprint(e.target.value)}><option value="">Backlog</option>{(sprints ?? []).filter((s) => s.state !== "closed").map((s) => <option key={s.id} value={s.id}>{s.name}{s.state === "active" ? " · active" : ""}</option>)}</Select></Field>
        </div>
        <Field label="Labels"><LabelPicker projectId={projectId} value={labels} onChange={setLabels} /></Field>
        <Field label="Description" hint="Markdown. You can add acceptance criteria after creating."><Textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Optional context…" className="min-h-[70px]" /></Field>
        {!projectId && <p className="text-xs text-rust-light">Pick a project first — or <button type="button" className="underline" onClick={() => nav("/welcome")}>create one</button>.</p>}
      </div>
    </Modal>
  );
}
