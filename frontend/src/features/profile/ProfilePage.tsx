// Pick who you are. No passwords; optional PIN protects private action items.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useProfiles, useLogin } from "@/api/queries";
import { Avatar, Button, Input, Panel, cn, toast } from "@/components/ui";
import { ApiError } from "@/api/client";

export default function ProfilePage() {
  const { data: profiles } = useProfiles();
  const login = useLogin();
  const nav = useNavigate();
  const [picked, setPicked] = useState<string | null>(null);
  const [pin, setPin] = useState("");
  const go = (id: string, p?: string) => login.mutate({ user_id: id, pin: p }, {
    onSuccess: (u) => { toast.fun(`Welcome back, ${u.name}.`, "Picking up where you left off."); nav("/"); },
    onError: (e) => { if (e instanceof ApiError && e.status === 403) { setPicked(id); toast.error("That PIN didn't match."); } else toast.error("Couldn't sign in", String(e)); },
  });
  return (
    <div className="min-h-screen grid-bg flex items-center justify-center p-6">
      <Panel cut className="w-full max-w-[720px] p-8">
        <div className="hairline mb-6" />
        <div className="eyebrow">Hyperlane</div>
        <h1 className="text-3xl mt-1">Pick your profile</h1>
        <p className="text-text-3 mt-1">No passwords. Add a PIN on your profile if you want your private checklist locked.</p>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3 mt-6">
          {profiles?.map((p) => (
            <button key={p.id} onClick={() => (picked === p.id ? undefined : go(p.id))} className={cn("panel p-4 flex flex-col items-center gap-2 hover:border-gold transition-colors", picked === p.id && "border-gold glow-gold")}>
              <Avatar user={p} size={48} />
              <div className="font-display font-semibold">{p.name}</div>
              <div className="text-[11px] text-text-3">{p.role}</div>
              {picked === p.id && (
                <form onSubmit={(e) => { e.preventDefault(); go(p.id, pin); }} className="w-full mt-1 flex gap-1" onClick={(e) => e.stopPropagation()}>
                  <Input autoFocus type="password" inputMode="numeric" placeholder="PIN" value={pin} onChange={(e) => setPin(e.target.value)} className="h-8 text-center" />
                  <Button size="sm" variant="primary" type="submit">Go</Button>
                </form>
              )}
            </button>
          ))}
        </div>
        {profiles && profiles.length === 0 && <p className="mt-6 text-sm text-text-2">No profiles yet. <a href="/welcome">Run the welcome setup</a> to create the first one.</p>}
        <div className="mt-6 flex items-center justify-between text-xs text-text-3"><span>Everything stays on this machine.</span><a href="/welcome">Setup wizard →</a></div>
      </Panel>
    </div>
  );
}
