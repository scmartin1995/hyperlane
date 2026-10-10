import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMe, useProjects } from "@/api/queries";
import { useUI } from "@/lib/store";
import { Button, Field, Input, Modal, Select, Textarea, toast } from "@/components/ui";
import { useIntakeMutations } from "./hooks";

export function NewRequestModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { create } = useIntakeMutations();
  const { data: projects } = useProjects(); const { data: me } = useMe();
  const pid = useUI((s) => s.projectId);
  const nav = useNavigate();
  const [f, setF] = useState({ subject: "", body: "", requester_name: "", requester_email: "", project_id: pid ?? "" });
  const submit = () => {
    if (!f.subject.trim() || !f.body.trim()) return toast.error("Subject and details are required");
    create.mutate({ subject: f.subject.trim(), body: f.body.trim(), requester_name: f.requester_name || me?.name, requester_email: f.requester_email || me?.email || undefined, project_id: f.project_id || null, channel: "web" },
      { onSuccess: (r) => { toast.success("Request logged", "The agent is analyzing it now."); onClose(); setF({ subject: "", body: "", requester_name: "", requester_email: "", project_id: pid ?? "" }); nav(`/intake/${r.id}`); }, onError: (e) => toast.error("Couldn't create the request", (e as Error).message) });
  };
  return (
    <Modal open={open} onClose={onClose} eyebrow="Web intake" title="New request" footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={create.isPending} onClick={submit}>Submit &amp; analyze</Button></>}>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <Field label="Subject" required><Input autoFocus value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} placeholder="Customers can't export invoices" /></Field>
        <Field label="Details" required hint="Ctrl+Enter submits. The more context, the fewer questions the agent asks."><Textarea value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} className="min-h-[140px]" onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") submit(); }} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Requester name"><Input value={f.requester_name} onChange={(e) => setF({ ...f, requester_name: e.target.value })} placeholder={me?.name ?? ""} /></Field>
          <Field label="Requester email"><Input type="email" value={f.requester_email} onChange={(e) => setF({ ...f, requester_email: e.target.value })} /></Field>
        </div>
        <Field label="Project"><Select value={f.project_id} onChange={(e) => setF({ ...f, project_id: e.target.value })}><option value="">Decide later</option>{projects?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field>
      </form>
    </Modal>
  );
}
