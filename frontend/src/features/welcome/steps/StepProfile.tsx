import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, UserPlus } from "lucide-react";
import { api } from "@/api/client";
import { useMe } from "@/api/queries";
import type { User } from "@/api/types";
import { Avatar, Button, Field, Input, cn, toast } from "@/components/ui";
import { EMOJIS, SWATCHES, type StepProps } from "../state";

export function StepProfile({ next, back }: StepProps) {
  const { data: me } = useMe();
  const qc = useQueryClient();
  const [addingAnother, setAddingAnother] = useState(false);
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [emoji, setEmoji] = useState(EMOJIS[0]);
  const [color, setColor] = useState(SWATCHES[0]);
  const [pin, setPin] = useState("");
  const create = useMutation({
    mutationFn: async () => {
      const user = await api.post<User>("/users", { name: name.trim(), role: role.trim() || "Developer", emoji, color });
      await api.post<User>("/auth/login", { user_id: user.id });
      if (pin.trim()) await api.post("/auth/pin", { pin: pin.trim() });
      return user;
    },
    onSuccess: async (u) => { await qc.invalidateQueries(); toast.fun(`Welcome, ${u.name}.`, "Let's set up your project."); next(); },
    onError: (e) => toast.error("Couldn't create your profile", String(e)),
  });
  const pinOk = !pin || /^\d{4,8}$/.test(pin);
  const preview = { id: "preview", name: name || "You", handle: "", emoji, color, role };

  if (me && !addingAnother) return (
    <div className="space-y-6">
      <div><div className="eyebrow">Step 2 · Profile</div><h2 className="text-2xl mt-1">You're already signed in</h2><p className="text-text-3 text-sm mt-1">Signed in and ready. Continue, or add a teammate's profile now.</p></div>
      <div className="panel panel-cut p-5 flex items-center gap-4 glow-gold"><Avatar user={me} size={56} /><div><div className="font-display font-bold text-lg">{me.name}</div><div className="text-text-3 text-sm">{me.role}{me.has_pin ? " · PIN set" : ""}</div></div></div>
      <div className="flex justify-between"><Button variant="ghost" icon={ArrowLeft} onClick={back}>Back</Button><div className="flex gap-2"><Button variant="outline" icon={UserPlus} onClick={() => setAddingAnother(true)}>Add another profile</Button><Button variant="primary" size="lg" iconRight={ArrowRight} onClick={next}>Continue</Button></div></div>
    </div>
  );

  return (
    <form className="space-y-5" onSubmit={(e) => { e.preventDefault(); if (name.trim() && pinOk) create.mutate(); }}>
      <div><div className="eyebrow">Step 2 · Profile</div><h2 className="text-2xl mt-1">Create your profile</h2><p className="text-text-3 text-sm mt-1">No passwords, no email required. Profiles are how Hyperlane knows whose checklist is whose.</p></div>
      <div className="flex items-start gap-5">
        <div className="shrink-0 flex flex-col items-center gap-2 pt-1"><Avatar user={preview} size={72} /><span className="text-[11px] text-text-3">preview</span></div>
        <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Name" required><Input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Anakin Skywalker" /></Field>
          <Field label="Role"><Input value={role} onChange={(e) => setRole(e.target.value)} placeholder="Product lead, engineer, QA…" /></Field>
          <Field label="PIN (optional)" hint={pinOk ? "4–8 digits. Locks your private action items." : "Use 4–8 digits."} className="sm:col-span-2"><Input type="password" inputMode="numeric" value={pin} onChange={(e) => setPin(e.target.value)} placeholder="••••" className={cn("w-40", !pinOk && "border-rust")} /></Field>
        </div>
      </div>
      <div>
        <span className="block mb-1.5 text-xs font-display font-semibold tracking-wide text-text-2 uppercase">Emoji</span>
        <div className="flex flex-wrap gap-1" role="radiogroup" aria-label="Emoji">{EMOJIS.map((e) => <button type="button" key={e} role="radio" aria-checked={emoji === e} onClick={() => setEmoji(e)} className={cn("w-9 h-9 grid place-items-center rounded-[8px] text-xl border transition-transform hover:scale-110", emoji === e ? "border-gold bg-gold/15" : "border-transparent hover:border-border")}>{e}</button>)}</div>
      </div>
      <div>
        <span className="block mb-1.5 text-xs font-display font-semibold tracking-wide text-text-2 uppercase">Color</span>
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Color">{SWATCHES.map((c) => <button type="button" key={c} role="radio" aria-checked={color === c} aria-label={c} onClick={() => setColor(c)} className={cn("w-8 h-8 rounded-full border-2 transition-transform hover:scale-110", color === c ? "border-text scale-110" : "border-transparent")} style={{ background: c }} />)}</div>
      </div>
      <div className="flex justify-between"><Button type="button" variant="ghost" icon={ArrowLeft} onClick={() => (me ? setAddingAnother(false) : back())}>Back</Button><Button type="submit" variant="primary" size="lg" iconRight={ArrowRight} loading={create.isPending} disabled={!name.trim() || !pinOk}>Create & sign in</Button></div>
    </form>
  );
}
