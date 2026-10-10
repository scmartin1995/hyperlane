import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Sparkles, FileSpreadsheet, Trophy, Square } from "lucide-react";
import { api } from "@/api/client";
import { useProjects } from "@/api/queries";
import type { SeedResult } from "@/api/types";
import { useUI } from "@/lib/store";
import { Button, cn, toast } from "@/components/ui";
import type { StepProps } from "../state";
import { SeedAgent } from "./SeedAgent";
import { SeedImport } from "./SeedImport";

type Option = "agent" | "import" | "demo" | "empty";
const OPTIONS: { key: Option; icon: typeof Sparkles; title: string; sub: string; accent: string }[] = [
  { key: "agent", icon: Sparkles, title: "Build it with the assistant", sub: "Describe the product; get epics → features → stories.", accent: "var(--gold)" },
  { key: "import", icon: FileSpreadsheet, title: "Import from Excel/CSV", sub: "Bring an existing backlog. We map the columns.", accent: "var(--teal)" },
  { key: "demo", icon: Trophy, title: "Load the demo project", sub: "5 people, 56 items, 4 sprints of history. Explore everything.", accent: "var(--purple-light)" },
  { key: "empty", icon: Square, title: "Start empty", sub: "A clean backlog. Add items as you go.", accent: "var(--smoke)" },
];

export function StepSeed({ state, update, next, back }: StepProps) {
  const ui = useUI();
  const qc = useQueryClient();
  const { data: projects } = useProjects();
  const [opt, setOpt] = useState<Option | null>(null);
  const projectId = state.projectId ?? projects?.[0]?.id ?? null;
  const seed = useMutation({
    mutationFn: () => api.post<SeedResult>("/dev/seed", {}),
    onSuccess: (r) => { const p = r.project; if (p) { update({ projectId: p.id, seeded: "demo" }); ui.setProjectId(p.id); } else update({ seeded: "demo" }); qc.invalidateQueries(); toast.fun("Demo project loaded", "Atlas Customer Portal: four sprints of history to explore."); next(); },
    onError: (e) => toast.error("Couldn't load the demo", String(e)),
  });
  return (
    <div className="space-y-5">
      <div><div className="eyebrow">Step 4 · Backlog</div><h2 className="text-2xl mt-1">Seed the backlog</h2><p className="text-text-3 text-sm mt-1">How should the first backlog get here? You can do any of these again later from the backlog page.</p></div>
      {!projectId && <p className="text-sm text-rust-light">No project yet — go back one step to create one.</p>}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" role="radiogroup" aria-label="Seed option">
        {OPTIONS.map((o) => (
          <button type="button" key={o.key} role="radio" aria-checked={opt === o.key} disabled={!projectId && o.key !== "demo"} onClick={() => setOpt(o.key)} className={cn("panel panel-cut p-4 text-left transition-all hover:border-gold disabled:opacity-50", opt === o.key && "border-gold glow-gold")}>
            <o.icon size={18} style={{ color: o.accent }} /><div className="font-display font-bold mt-2">{o.title}</div><div className="text-xs text-text-3">{o.sub}</div>
          </button>
        ))}
      </div>
      {opt === "agent" && projectId && <SeedAgent projectId={projectId} onDone={() => { update({ seeded: "agent" }); next(); }} />}
      {opt === "import" && projectId && <SeedImport projectId={projectId} onDone={() => { update({ seeded: "import" }); next(); }} />}
      {opt === "demo" && <div className="panel p-4 flex items-center justify-between gap-3 animate-in"><p className="text-sm text-text-2">Creates a “Atlas Customer Portal” project with five people, ~45 items, three closed sprints and one in progress. Safe to delete later.</p><Button variant="teal" icon={Trophy} loading={seed.isPending} onClick={() => seed.mutate()}>Load demo</Button></div>}
      {opt === "empty" && <div className="panel p-4 flex items-center justify-between gap-3 animate-in"><p className="text-sm text-text-2">Fresh asphalt. Press <kbd className="font-mono text-xs border border-border-strong rounded px-1">c</kbd> anywhere to create an item.</p><Button variant="primary" iconRight={ArrowRight} onClick={() => { update({ seeded: "empty" }); next(); }}>Continue</Button></div>}
      <div className="flex justify-between"><Button variant="ghost" icon={ArrowLeft} onClick={back}>Back</Button>{state.seeded && <Button variant="ghost" iconRight={ArrowRight} onClick={next}>Skip — already seeded</Button>}</div>
    </div>
  );
}
