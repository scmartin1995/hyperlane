import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTemplates, useUsers } from "@/api/queries";
import { useUI } from "@/lib/store";
import { Button, Field, Input, Modal, Select, Textarea, cn, toast } from "@/components/ui";
import { useCreateProject } from "./hooks";

export function NewProjectModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data: templates } = useTemplates(); const { data: users } = useUsers();
  const create = useCreateProject();
  const ui = useUI(); const nav = useNavigate();
  const [f, setF] = useState({ name: "", key: "", template: "", description: "", icon: "🏁", color: "#e4b963", lead_id: "" });
  const tpl = f.template || templates?.[0]?.key || "";
  const submit = () => {
    if (!f.name.trim()) return toast.error("Give the project a name"); if (!tpl) return toast.error("Pick a template");
    create.mutate({ name: f.name.trim(), key: f.key.trim().toUpperCase() || undefined, template: tpl, description: f.description || undefined, icon: f.icon, color: f.color, lead_id: f.lead_id || null },
      { onSuccess: (p) => { toast.fun(`${p.name} created`); ui.setProjectId(p.id); onClose(); nav("/settings/project"); }, onError: (e) => toast.error("Couldn't create project", (e as Error).message) });
  };
  return (
    <Modal open={open} onClose={onClose} width={680} eyebrow="New project" title="Start a new project" footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={create.isPending} onClick={submit}>Create project</Button></>}>
      <div className="grid gap-2 sm:grid-cols-2 mb-4">
        {templates?.map((t) => (
          <button key={t.key} type="button" onClick={() => setF({ ...f, template: t.key })} className={cn("panel p-3 text-left hover:border-gold transition-colors", tpl === t.key && "border-gold glow-gold")}>
            <div className="flex items-center gap-2"><span className="text-xl">{t.icon}</span><div><div className="font-display font-bold">{t.name}</div><div className="text-[11px] text-text-3">{t.methodology} · {t.workflow.length} states · {t.item_types.length} types</div></div></div>
            <p className="text-xs text-text-2 mt-1">{t.tagline}</p>
          </button>
        ))}
        {!templates?.length && <p className="text-sm text-text-3">No templates available.</p>}
      </div>
      <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <Field label="Name" required><Input autoFocus value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Key" hint="Auto-derived if blank"><Input value={f.key} maxLength={6} className="num" onChange={(e) => setF({ ...f, key: e.target.value.toUpperCase() })} placeholder="HL" /></Field>
        <Field label="Description" className="sm:col-span-2"><Textarea value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} className="min-h-[56px]" /></Field>
        <Field label="Icon · color"><div className="flex gap-2"><Input value={f.icon} onChange={(e) => setF({ ...f, icon: e.target.value })} className="w-16 text-center" /><Input type="color" value={f.color} onChange={(e) => setF({ ...f, color: e.target.value })} className="w-16 p-1" /></div></Field>
        <Field label="Lead"><Select value={f.lead_id} onChange={(e) => setF({ ...f, lead_id: e.target.value })}><option value="">Nobody yet</option>{users?.filter((u) => u.is_active).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</Select></Field>
        <button type="submit" className="hidden" />
      </form>
    </Modal>
  );
}
