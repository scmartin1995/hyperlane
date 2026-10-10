import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Field, Input, Modal, Textarea, toast } from "@/components/ui";
import { useCreateUser } from "./hooks";

const EMOJI = ["🏎️", "🚀", "🛠️", "🎯", "🧭", "⚡", "🦾", "🪐", "🔥", "🧪"];
const COLORS = ["#e4b963", "#27cfc3", "#e07a5f", "#9b6bc0", "#67a671", "#306376", "#f0edeb", "#bc553c"];

export function AddPersonModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const create = useCreateUser();
  const nav = useNavigate();
  const [f, setF] = useState({ name: "", role: "", email: "", skills: "", hours_per_week: 40, focus_factor: 0.7, emoji: EMOJI[0], color: COLORS[1], bio: "" });
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((p) => ({ ...p, [k]: v }));
  const submit = () => {
    if (!f.name.trim()) return toast.error("A name is required");
    create.mutate({ name: f.name.trim(), role: f.role || undefined, email: f.email || undefined, skills: f.skills.split(",").map((s) => s.trim()).filter(Boolean), hours_per_week: f.hours_per_week, focus_factor: f.focus_factor, emoji: f.emoji, color: f.color, bio: f.bio || undefined },
      { onSuccess: (u) => { toast.fun(`${u.name} joined the crew`); onClose(); setF((p) => ({ ...p, name: "", role: "", email: "", skills: "", bio: "" })); nav(`/people/${u.id}`); }, onError: (e) => toast.error("Couldn't add person", (e as Error).message) });
  };
  return (
    <Modal open={open} onClose={onClose} eyebrow="New crew member" title="Add a person" footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={create.isPending} onClick={submit}>Add person</Button></>}>
      <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <Field label="Name" required className="sm:col-span-2"><Input autoFocus value={f.name} onChange={(e) => set("name", e.target.value)} placeholder="Ada Lovelace" /></Field>
        <Field label="Role"><Input value={f.role} onChange={(e) => set("role", e.target.value)} placeholder="Engineer, Designer, PM…" /></Field>
        <Field label="Email" hint="Used to match Slack and email intake."><Input type="email" value={f.email} onChange={(e) => set("email", e.target.value)} /></Field>
        <Field label="Skills" hint="Comma separated" className="sm:col-span-2"><Input value={f.skills} onChange={(e) => set("skills", e.target.value)} placeholder="react, python, sql" /></Field>
        <Field label="Hours / week"><Input type="number" min={0} max={80} className="num" value={f.hours_per_week} onChange={(e) => set("hours_per_week", Number(e.target.value))} /></Field>
        <Field label="Focus factor" hint="Share of hours that go to sprint work (0–1)."><Input type="number" min={0} max={1} step={0.05} className="num" value={f.focus_factor} onChange={(e) => set("focus_factor", Number(e.target.value))} /></Field>
        <Field label="Emoji"><div className="flex flex-wrap gap-1">{EMOJI.map((e) => <button type="button" key={e} onClick={() => set("emoji", e)} className={`text-xl p-1 rounded ${f.emoji === e ? "bg-surface-3 ring-1 ring-gold" : ""}`} aria-label={e}>{e}</button>)}</div></Field>
        <Field label="Color"><div className="flex flex-wrap gap-1.5 pt-1">{COLORS.map((c) => <button type="button" key={c} onClick={() => set("color", c)} className={`w-7 h-7 rounded-full ${f.color === c ? "ring-2 ring-offset-2 ring-offset-surface ring-gold" : ""}`} style={{ background: c }} aria-label={c} />)}</div></Field>
        <Field label="Bio" className="sm:col-span-2"><Textarea value={f.bio} onChange={(e) => set("bio", e.target.value)} className="min-h-[60px]" onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") submit(); }} /></Field>
        <button type="submit" className="hidden" />
      </form>
    </Modal>
  );
}
