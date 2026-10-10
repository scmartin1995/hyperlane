import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Archive, Plus, Save } from "lucide-react";
import type { Project, ProjectSettings } from "@/api/types";
import { useProject, useUsers } from "@/api/queries";
import { useUI } from "@/lib/store";
import { Button, Field, Input, Select, Skeleton, Textarea, toast } from "@/components/ui";
import { WorkflowEditor } from "./WorkflowEditor";
import { ItemTypesEditor } from "./ItemTypesEditor";
import { LabelsManager } from "./LabelsManager";
import { NewProjectModal } from "./NewProjectModal";
import { useArchiveProject, useUpdateProject } from "./hooks";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function ProjectTab({ pid }: { pid: string }) {
  const { data: p, isLoading } = useProject(pid);
  const [showNew, setShowNew] = useState(false);
  if (isLoading || !p) return <Skeleton className="h-64" />;
  return (
    <div className="space-y-4">
      <div className="flex justify-end"><Button variant="outline" icon={Plus} onClick={() => setShowNew(true)}>New project</Button></div>
      <Basics project={p} />
      <div className="grid gap-4 lg:grid-cols-2">
        <WorkflowEditor project={p} />
        <ItemTypesEditor project={p} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Estimation project={p} />
        <LabelsManager pid={p.id} />
      </div>
      <Danger project={p} />
      <NewProjectModal open={showNew} onClose={() => setShowNew(false)} />
    </div>
  );
}

function Basics({ project: p }: { project: Project }) {
  const update = useUpdateProject(p.id);
  const { data: users } = useUsers();
  const [f, setF] = useState({ name: p.name, key: p.key, description: p.description ?? "", color: p.color, icon: p.icon, lead_id: p.lead_id ?? "", slack_channel: p.slack_channel ?? "" });
  useEffect(() => setF({ name: p.name, key: p.key, description: p.description ?? "", color: p.color, icon: p.icon, lead_id: p.lead_id ?? "", slack_channel: p.slack_channel ?? "" }), [p]);
  const save = () => update.mutate({ ...f, description: f.description || null, lead_id: f.lead_id || null, slack_channel: f.slack_channel || null, key: f.key.toUpperCase() }, { onSuccess: () => toast.success("Project saved"), onError: (e) => toast.error("Couldn't save", (e as Error).message) });
  return (
    <section className="panel p-4">
      <div className="flex items-center justify-between mb-3"><div><div className="eyebrow">Project</div><h2 className="text-base">{p.icon} {p.name}</h2></div><Button size="sm" variant="primary" icon={Save} loading={update.isPending} onClick={save}>Save</Button></div>
      <form className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" onSubmit={(e) => { e.preventDefault(); save(); }}>
        <Field label="Name" className="lg:col-span-2"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Key" hint="Prefix for item keys (HL-42). Changing it renames every key."><Input value={f.key} maxLength={6} onChange={(e) => setF({ ...f, key: e.target.value.toUpperCase() })} className="num" /></Field>
        <Field label="Icon · color"><div className="flex gap-2"><Input value={f.icon} onChange={(e) => setF({ ...f, icon: e.target.value })} className="w-16 text-center" /><Input type="color" value={f.color} onChange={(e) => setF({ ...f, color: e.target.value })} className="w-16 p-1" /></div></Field>
        <Field label="Description" className="sm:col-span-2 lg:col-span-4"><Textarea value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} className="min-h-[60px]" /></Field>
        <Field label="Lead" className="lg:col-span-2"><Select value={f.lead_id} onChange={(e) => setF({ ...f, lead_id: e.target.value })}><option value="">Nobody yet</option>{users?.filter((u) => u.is_active).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</Select></Field>
        <Field label="Slack channel" hint="Where sprint and item updates post." className="lg:col-span-2"><Input value={f.slack_channel} onChange={(e) => setF({ ...f, slack_channel: e.target.value })} placeholder="#customer-portal" /></Field>
        <button type="submit" className="hidden" />
      </form>
    </section>
  );
}

function Estimation({ project: p }: { project: Project }) {
  const update = useUpdateProject(p.id);
  const s = p.settings;
  const [f, setF] = useState({ estimation: s.estimation, scale: s.points_scale.join(", "), sprint_length_days: s.sprint_length_days, working_days: s.working_days, default_type: s.default_type });
  useEffect(() => setF({ estimation: s.estimation, scale: s.points_scale.join(", "), sprint_length_days: s.sprint_length_days, working_days: s.working_days, default_type: s.default_type }), [s]);
  const save = () => {
    const points_scale = f.scale.split(",").map((x) => Number(x.trim())).filter((n) => !Number.isNaN(n) && n >= 0);
    const settings: ProjectSettings = { ...s, estimation: f.estimation, points_scale, sprint_length_days: Math.max(1, f.sprint_length_days), working_days: f.working_days, default_type: f.default_type };
    update.mutate({ settings }, { onSuccess: () => toast.success("Settings saved"), onError: (e) => toast.error("Couldn't save", (e as Error).message) });
  };
  const toggleDay = (d: number) => setF((x) => ({ ...x, working_days: x.working_days.includes(d) ? x.working_days.filter((y) => y !== d) : [...x.working_days, d].sort() }));
  return (
    <section className="panel p-4">
      <div className="flex items-center justify-between mb-3"><div><div className="eyebrow">Planning</div><h2 className="text-base">Estimation &amp; cadence</h2></div><Button size="sm" variant="primary" icon={Save} loading={update.isPending} onClick={save}>Save</Button></div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Estimation mode"><Select value={f.estimation} onChange={(e) => setF({ ...f, estimation: e.target.value as ProjectSettings["estimation"] })}><option value="points">Story points</option><option value="hours">Hours</option><option value="throughput">Throughput (count items)</option></Select></Field>
        <Field label="Points scale" hint="Comma separated"><Input value={f.scale} onChange={(e) => setF({ ...f, scale: e.target.value })} className="num" placeholder="1, 2, 3, 5, 8, 13" /></Field>
        <Field label="Sprint length (days)"><Input type="number" min={1} max={60} className="num" value={f.sprint_length_days} onChange={(e) => setF({ ...f, sprint_length_days: Number(e.target.value) })} /></Field>
        <Field label="Default item type"><Select value={f.default_type} onChange={(e) => setF({ ...f, default_type: e.target.value })}>{p.item_types.map((t) => <option key={t.key} value={t.key}>{t.icon} {t.name}</option>)}</Select></Field>
        <Field label="Working days" className="sm:col-span-2"><div className="flex gap-1">{DAYS.map((d, i) => <button type="button" key={d} onClick={() => toggleDay(i)} className={`h-8 px-2.5 rounded-[6px] text-xs font-display font-semibold border ${f.working_days.includes(i) ? "bg-teal/20 border-teal text-teal" : "border-border text-text-3"}`} aria-pressed={f.working_days.includes(i)}>{d}</button>)}</div></Field>
      </div>
    </section>
  );
}

function Danger({ project: p }: { project: Project }) {
  const archive = useArchiveProject();
  const ui = useUI(); const nav = useNavigate();
  return (
    <section className="panel p-4 border-rust/40">
      <div className="flex items-center justify-between gap-3"><div><div className="eyebrow text-rust-light">Danger zone</div><h2 className="text-base">Archive this project</h2><p className="text-xs text-text-3 mt-1">Hides it from the project picker and reports. Nothing is deleted; items stay in the database.</p></div>
        <Button variant="danger" icon={Archive} loading={archive.isPending} onClick={() => { if (prompt(`Type ${p.key} to archive this project`) === p.key) archive.mutate(p.id, { onSuccess: () => { toast.info("Project archived"); ui.setProjectId(null); nav("/"); }, onError: (e) => toast.error("Couldn't archive", (e as Error).message) }); }}>Archive</Button></div>
    </section>
  );
}
