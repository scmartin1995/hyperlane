import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, KeyRound, Save } from "lucide-react";
import type { User } from "@/api/types";
import { useMe, useProject } from "@/api/queries";
import { stateOf } from "@/lib/format";
import { Avatar, Badge, Button, EmptyState, Field, Input, Skeleton, Textarea, Toggle, toast } from "@/components/ui";
import { ItemDrawer, useProjectId } from "@/features/sprints/common";
import { LearnedCapacity } from "./LearnedCapacity";
import { useSetPin, useUpdateUser, useUser, useUserItems } from "./hooks";

export function PersonDetail({ userId }: { userId: string }) {
  const { data: u, isLoading, isError } = useUser(userId);
  const { data: me } = useMe();
  const pid = useProjectId();
  const { data: project } = useProject(pid ?? undefined);
  const items = useUserItems(pid, userId);
  const [open, setOpen] = useState<string | null>(null);
  if (isLoading) return <div className="space-y-3"><Skeleton className="h-10 w-72" /><Skeleton className="h-64" /></div>;
  if (isError || !u) return <EmptyState icon="🛰️" title="Person not found" action={<Link to="/people"><Button>Back</Button></Link>} />;
  const isMe = me?.id === u.id;
  return (
    <div>
      <Link to="/people" className="inline-flex items-center gap-1 text-xs text-text-3 hover:text-text no-underline"><ArrowLeft size={12} /> Team</Link>
      <div className="flex items-center gap-3 mt-1 mb-4"><Avatar user={u} size={48} /><div><h1 className="text-2xl leading-none">{u.name}</h1><p className="text-text-3 text-sm mt-1">{u.role || "No role"} · @{u.handle}{isMe && " · this is you"}</p></div>{!u.is_active && <Badge>inactive</Badge>}</div>
      <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
        <div className="space-y-4">
          <ProfileForm user={u} isMe={isMe} />
          {pid && <LearnedCapacity pid={pid} userId={u.id} />}
        </div>
        <div className="space-y-4">
          {isMe && <PinPanel user={u} />}
          <Preferences user={u} isMe={isMe} />
          <section className="panel p-4">
            <div className="eyebrow">Current work</div><h2 className="text-base mb-2">{project ? `Open items in ${project.key}` : "Open items"}</h2>
            {items.isLoading ? <Skeleton className="h-20" /> : !items.data?.length ? <p className="text-sm text-text-3">Nothing assigned right now.</p> : (
              <ul className="space-y-1">{items.data.map((it) => { const st = stateOf(project, it.status); return <li key={it.id}><button onClick={() => setOpen(it.id)} className="w-full text-left flex items-center gap-2 text-sm px-2 py-1.5 rounded hover:bg-surface-2"><span className="num text-xs text-text-3 w-16 shrink-0">{it.key}</span><span className="truncate flex-1">{it.title}</span><Badge size="xs" color={st?.color} dot>{st?.name ?? it.status}</Badge></button></li>; })}</ul>
            )}
          </section>
        </div>
      </div>
      <ItemDrawer itemId={open} onClose={() => setOpen(null)} />
    </div>
  );
}

function ProfileForm({ user: u, isMe }: { user: User; isMe: boolean }) {
  const update = useUpdateUser(u.id);
  const [f, setF] = useState({ name: u.name, role: u.role, email: u.email ?? "", skills: u.skills.join(", "), hours_per_week: u.hours_per_week, focus_factor: u.focus_factor, timezone: u.timezone, slack_user_id: u.slack_user_id ?? "", bio: u.bio ?? "", emoji: u.emoji, color: u.color, is_active: u.is_active });
  useEffect(() => setF({ name: u.name, role: u.role, email: u.email ?? "", skills: u.skills.join(", "), hours_per_week: u.hours_per_week, focus_factor: u.focus_factor, timezone: u.timezone, slack_user_id: u.slack_user_id ?? "", bio: u.bio ?? "", emoji: u.emoji, color: u.color, is_active: u.is_active }), [u]);
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((p) => ({ ...p, [k]: v }));
  const save = () => update.mutate({ ...f, email: f.email || null, slack_user_id: f.slack_user_id || null, bio: f.bio || null, skills: f.skills.split(",").map((s) => s.trim()).filter(Boolean) }, { onSuccess: () => toast.success("Profile saved"), onError: (e) => toast.error("Couldn't save", (e as Error).message) });
  return (
    <section className="panel p-4">
      <div className="flex items-center justify-between mb-3"><div><div className="eyebrow">Profile</div><h2 className="text-base">Details</h2></div><Button size="sm" variant="primary" icon={Save} loading={update.isPending} onClick={save}>Save</Button></div>
      <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); save(); }}>
        <Field label="Name"><Input value={f.name} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Role"><Input value={f.role} onChange={(e) => set("role", e.target.value)} /></Field>
        <Field label="Email"><Input type="email" value={f.email} onChange={(e) => set("email", e.target.value)} /></Field>
        <Field label="Slack user ID" hint="e.g. U0123ABCD — used for DMs and mentions."><Input value={f.slack_user_id} onChange={(e) => set("slack_user_id", e.target.value)} /></Field>
        <Field label="Skills" hint="Comma separated" className="sm:col-span-2"><Input value={f.skills} onChange={(e) => set("skills", e.target.value)} /></Field>
        <Field label="Hours / week"><Input type="number" min={0} max={80} className="num" value={f.hours_per_week} onChange={(e) => set("hours_per_week", Number(e.target.value))} /></Field>
        <Field label="Focus factor" hint="Share of hours for sprint work."><Input type="number" min={0} max={1} step={0.05} className="num" value={f.focus_factor} onChange={(e) => set("focus_factor", Number(e.target.value))} /></Field>
        <Field label="Timezone"><Input value={f.timezone} onChange={(e) => set("timezone", e.target.value)} /></Field>
        <Field label="Emoji · color"><div className="flex gap-2"><Input value={f.emoji} onChange={(e) => set("emoji", e.target.value)} className="w-16 text-center" /><Input type="color" value={f.color} onChange={(e) => set("color", e.target.value)} className="w-16 p-1" /></div></Field>
        <Field label="Bio" className="sm:col-span-2"><Textarea value={f.bio} onChange={(e) => set("bio", e.target.value)} className="min-h-[60px]" onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") save(); }} /></Field>
        {!isMe && <div className="sm:col-span-2"><Toggle checked={f.is_active} onChange={(v) => set("is_active", v)} label="Active (inactive people are hidden from planning)" /></div>}
        <button type="submit" className="hidden" />
      </form>
    </section>
  );
}

function PinPanel({ user: u }: { user: User }) {
  const setPin = useSetPin();
  const [pin, setPinV] = useState("");
  return (
    <section className="panel p-4">
      <div className="eyebrow">Privacy</div><h2 className="text-base mb-1">Profile PIN</h2>
      <p className="text-xs text-text-3 mb-3">{u.has_pin ? "A PIN is set. Anyone picking your profile needs it." : "No PIN. Anyone at this machine can pick your profile and see your private checklist."}</p>
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (pin.length < 4) return toast.error("Use at least 4 digits"); setPin.mutate(pin, { onSuccess: () => { toast.success("PIN set"); setPinV(""); }, onError: (er) => toast.error("Couldn't set PIN", (er as Error).message) }); }}>
        <Input type="password" inputMode="numeric" placeholder="New PIN" value={pin} onChange={(e) => setPinV(e.target.value)} className="h-8" /><Button size="sm" type="submit" icon={KeyRound} loading={setPin.isPending}>Set</Button>
        {u.has_pin && <Button size="sm" variant="ghost" onClick={() => setPin.mutate(null, { onSuccess: () => toast.info("PIN cleared"), onError: (er) => toast.error("Couldn't clear PIN", (er as Error).message) })}>Clear</Button>}
      </form>
    </section>
  );
}

function Preferences({ user: u, isMe }: { user: User; isMe: boolean }) {
  const update = useUpdateUser(u.id);
  const prefs = u.preferences ?? {};
  const setPref = (k: string, v: boolean) => update.mutate({ preferences: { ...prefs, [k]: v } }, { onError: (e) => toast.error("Couldn't save preference", (e as Error).message) });
  return (
    <section className="panel p-4 space-y-2">
      <div className="eyebrow">Notifications</div><h2 className="text-base">{isMe ? "How to reach you" : `How to reach ${u.name.split(" ")[0]}`}</h2>
      <Toggle checked={!!prefs.slack_dm} onChange={(v) => setPref("slack_dm", v)} label="Daily digest by Slack DM" />
      <Toggle checked={prefs.notify_assignments !== false} onChange={(v) => setPref("notify_assignments", v)} label="Notify me when I'm assigned work" />
      <p className="text-[11px] text-text-3">Only sent if Slack is configured in Settings → Integrations.</p>
    </section>
  );
}
