import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Moon, Sun } from "lucide-react";
import { api } from "@/api/client";
import { qk } from "@/api/queries";
import type { Workspace } from "@/api/types";
import { useUI, LABELS } from "@/lib/store";
import { Button, Field, Input, Toggle, cn, toast } from "@/components/ui";
import type { StepProps } from "../state";

export function StepWorkspace({ state, update, next }: StepProps) {
  const ui = useUI();
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: () => api.patch<Workspace>("/workspace", { name: state.wsName.trim() || "Hyperlane", theme: state.theme, flavor: state.flavor }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: qk.workspace }); next(); },
    onError: (e) => toast.error("Couldn't save the workspace", String(e)),
  });
  const pickTheme = (t: "dark" | "light") => { ui.setTheme(t); update({ theme: t }); };
  return (
    <form className="space-y-6" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <div><div className="eyebrow">Step 1 · Workspace</div><h2 className="text-2xl mt-1">Name the league</h2><p className="text-text-3 text-sm mt-1">This is the name on the sidebar. Your team, your product, your garage — whatever you call it.</p></div>
      <Field label="Workspace name" required><Input autoFocus value={state.wsName} onChange={(e) => update({ wsName: e.target.value })} placeholder="e.g. Boonta Eve Racing" className="h-11 text-base" /></Field>
      <div>
        <span className="block mb-2 text-xs font-display font-semibold tracking-wide text-text-2 uppercase">Theme</span>
        <div className="grid grid-cols-2 gap-3">
          {([["dark", "Dark HUD", "Night race. Gold hairlines on coal.", Moon], ["light", "Paddock light", "Daylight. Rust accents on sand.", Sun]] as const).map(([k, title, sub, Icon]) => (
            <button type="button" key={k} onClick={() => pickTheme(k)} aria-pressed={state.theme === k} className={cn("panel panel-cut p-4 text-left transition-all hover:border-gold", state.theme === k && "border-gold glow-gold")}>
              <Icon size={18} className={state.theme === k ? "text-gold" : "text-text-3"} />
              <div className="font-display font-bold mt-2">{title}</div><div className="text-xs text-text-3">{sub}</div>
            </button>
          ))}
        </div>
      </div>
      <div className="panel p-4 flex items-start gap-4">
        <Toggle checked={state.flavor} onChange={(f) => { ui.setFlavor(f); update({ flavor: f }); }} label={<span className="font-display font-semibold">Racing flavor</span>} />
        <div className="text-xs text-text-3 flex-1">Playful labels with plain subtitles so nobody gets lost. Example: <span className="text-text">{state.flavor ? LABELS.home.fun : LABELS.home.plain}</span>{state.flavor && <span> · {LABELS.home.plain}</span>}, <span className="text-text">{state.flavor ? LABELS.board.fun : LABELS.board.plain}</span>{state.flavor && <span> · {LABELS.board.plain}</span>}. You can flip this any time in Settings.</div>
      </div>
      <div className="flex justify-end"><Button type="submit" variant="primary" size="lg" iconRight={ArrowRight} loading={save.isPending} disabled={!state.wsName.trim()}>Continue</Button></div>
    </form>
  );
}
