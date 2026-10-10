import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Save } from "lucide-react";
import { useWorkspace } from "@/api/queries";
import { useUI } from "@/lib/store";
import { Button, Field, Input, Select, Skeleton, Toggle, toast } from "@/components/ui";
import { useUpdateWorkspace } from "./hooks";

export function WorkspaceTab() {
  const { data: ws, isLoading } = useWorkspace();
  const update = useUpdateWorkspace();
  const ui = useUI();
  const [f, setF] = useState({ name: "", tagline: "", theme: "dark" as "dark" | "light" | "system", flavor: true });
  useEffect(() => { if (ws) setF({ name: ws.name, tagline: ws.tagline, theme: ws.theme, flavor: ws.flavor }); }, [ws]);
  if (isLoading) return <Skeleton className="h-64" />;
  const save = () => update.mutate(f, { onSuccess: () => { toast.success("Workspace saved"); ui.setFlavor(f.flavor); if (f.theme !== "system") ui.setTheme(f.theme); else ui.setTheme(window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"); }, onError: (e) => toast.error("Couldn't save", (e as Error).message) });
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <section className="panel p-4">
        <div className="flex items-center justify-between mb-3"><div><div className="eyebrow">Workspace</div><h2 className="text-base">Identity</h2></div><Button size="sm" variant="primary" icon={Save} loading={update.isPending} onClick={save}>Save</Button></div>
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save(); }}>
          <Field label="Name"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label="Tagline" hint="Shown on the welcome screen and home."><Input value={f.tagline} onChange={(e) => setF({ ...f, tagline: e.target.value })} placeholder="Plan, build and ship with an AI analyst on the team." /></Field>
          <Field label="Theme"><Select value={f.theme} onChange={(e) => setF({ ...f, theme: e.target.value as typeof f.theme })}><option value="dark">Dark</option><option value="light">Light</option><option value="system">Follow system</option></Select></Field>
          <Toggle checked={f.flavor} onChange={(v) => setF({ ...f, flavor: v })} label="Playful toasts and confetti" />
        </form>
      </section>
      <section className="panel p-4 self-start">
        <div className="eyebrow">Welcome</div><h3 className="font-display font-bold">Start over?</h3>
        <p className="text-sm text-text-3 mt-1 mb-3">Re-run the welcome flow to add a project from a template or load the demo project. Nothing gets deleted.</p>
        <Link to="/welcome"><Button variant="outline">Re-run welcome</Button></Link>
      </section>
    </div>
  );
}
