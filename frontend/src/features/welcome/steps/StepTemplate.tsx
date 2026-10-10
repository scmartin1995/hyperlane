import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import { api } from "@/api/client";
import { qk, useProject, useTemplates } from "@/api/queries";
import type { Project, Template } from "@/api/types";
import { useUI } from "@/lib/store";
import { Badge, Button, Field, Input, Select, Skeleton, cn, toast } from "@/components/ui";
import type { StepProps } from "../state";

export function StepTemplate({ state, update, next, back }: StepProps) {
  const ui = useUI();
  const qc = useQueryClient();
  const { data: templates, isLoading, isError } = useTemplates();
  const { data: existing } = useProject(state.projectId ?? undefined);
  const [createAnother, setCreateAnother] = useState(false);
  const [picked, setPicked] = useState<Template | null>(null);
  const [name, setName] = useState("");
  const [sprintLen, setSprintLen] = useState(14);
  const [estimation, setEstimation] = useState<Template["settings"]["estimation"]>("points");
  useEffect(() => { if (templates?.length && !picked) choose(templates[0]); }, [templates]); // eslint-disable-line react-hooks/exhaustive-deps
  const choose = (t: Template) => { setPicked(t); setSprintLen(t.settings.sprint_length_days); setEstimation(t.settings.estimation); };
  const create = useMutation({
    mutationFn: () => api.post<Project>("/projects", { name: name.trim(), template: picked!.key, settings: { ...picked!.settings, sprint_length_days: sprintLen, estimation } }),
    onSuccess: (p) => { update({ projectId: p.id }); ui.setProjectId(p.id); qc.invalidateQueries({ queryKey: qk.projects }); qc.invalidateQueries({ queryKey: qk.health }); toast.fun(`${p.name} created`, `Items will be numbered ${p.key}-1, ${p.key}-2…`); setCreateAnother(false); next(); },
    onError: (e) => toast.error("Couldn't create the project", String(e)),
  });

  if (existing && !createAnother) return (
    <div className="space-y-6">
      <div><div className="eyebrow">Step 3 · Project</div><h2 className="text-2xl mt-1">Project ready</h2><p className="text-text-3 text-sm mt-1">You already have a project. Continue with it, or build another.</p></div>
      <div className="panel panel-cut p-5 flex items-center gap-4 glow-gold"><span className="text-3xl">{existing.icon}</span><div><div className="font-display font-bold text-lg">{existing.name} <span className="num text-sm text-text-3">{existing.key}</span></div><div className="text-text-3 text-sm">{existing.methodology} · {existing.workflow.length} states · {existing.item_types.map((t) => t.plural).join(", ")}</div></div></div>
      <div className="flex justify-between"><Button variant="ghost" icon={ArrowLeft} onClick={back}>Back</Button><div className="flex gap-2"><Button variant="outline" onClick={() => setCreateAnother(true)}>Create another project</Button><Button variant="primary" size="lg" iconRight={ArrowRight} onClick={next}>Continue</Button></div></div>
    </div>
  );

  return (
    <form className="space-y-5" onSubmit={(e) => { e.preventDefault(); if (picked && name.trim()) create.mutate(); }}>
      <div><div className="eyebrow">Step 3 · Project</div><h2 className="text-2xl mt-1">Pick a project type</h2><p className="text-text-3 text-sm mt-1">Templates set item types, workflow and defaults. Everything is editable later in Settings.</p></div>
      {isLoading && <div className="grid grid-cols-2 gap-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)}</div>}
      {isError && <p className="text-sm text-rust-light">Couldn't load templates. Is the server running?</p>}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3" role="radiogroup" aria-label="Template">
        {templates?.map((t) => (
          <button type="button" key={t.key} role="radio" aria-checked={picked?.key === t.key} onClick={() => choose(t)} className={cn("panel panel-cut p-4 text-left transition-all hover:border-gold", picked?.key === t.key && "border-gold glow-gold")}>
            <div className="flex items-center gap-2"><span className="text-2xl">{t.icon}</span><div className="min-w-0"><div className="font-display font-bold">{t.name}</div><div className="text-xs text-text-3 truncate">{t.tagline}</div></div>{picked?.key === t.key && <Check size={16} className="ml-auto text-gold shrink-0" />}</div>
            <div className="mt-2 flex flex-wrap gap-1">{t.item_types.map((it) => <Badge key={it.key} size="xs" color={it.color}>{it.icon} {it.name}</Badge>)}</div>
            <div className="mt-1.5 flex flex-wrap gap-1">{t.workflow.map((w) => <Badge key={w.key} size="xs" dot color={w.color}>{w.name}</Badge>)}</div>
          </button>
        ))}
      </div>
      {picked && (
        <div className="panel p-4 grid grid-cols-1 sm:grid-cols-3 gap-3 animate-in">
          <Field label="Project name" required className="sm:col-span-3"><Input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder={`${state.wsName || "Our"} ${picked.name}`} /></Field>
          <Field label="Sprint length (days)"><Input type="number" min={1} max={60} className="num" value={sprintLen} onChange={(e) => setSprintLen(Math.max(1, Number(e.target.value) || 1))} /></Field>
          <Field label="Estimation"><Select value={estimation} onChange={(e) => setEstimation(e.target.value as typeof estimation)}><option value="points">Story points</option><option value="hours">Hours</option><option value="throughput">Throughput (count)</option></Select></Field>
          <div className="text-xs text-text-3 self-end pb-2">Methodology: <span className="text-text">{picked.methodology}</span></div>
        </div>
      )}
      <div className="flex justify-between"><Button type="button" variant="ghost" icon={ArrowLeft} onClick={() => (existing ? setCreateAnother(false) : back())}>Back</Button><Button type="submit" variant="primary" size="lg" iconRight={ArrowRight} loading={create.isPending} disabled={!picked || !name.trim()}>Create project</Button></div>
    </form>
  );
}
