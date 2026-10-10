// "Welcome to Hyperlane" — full-screen onboarding wizard. Survives refresh; re-runnable from Settings.
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check } from "lucide-react";
import { useHealth, useMe, useProjects, useWorkspace } from "@/api/queries";
import { useUI } from "@/lib/store";
import { Toaster, celebrate, cn, toast } from "@/components/ui";
import { STEPS, clearState, loadState, saveState, type WizardState } from "./state";
import { StepWorkspace } from "./steps/StepWorkspace";
import { StepProfile } from "./steps/StepProfile";
import { StepTemplate } from "./steps/StepTemplate";
import { StepSeed } from "./steps/StepSeed";
import { StepConnect } from "./steps/StepConnect";

export default function WelcomePage() {
  const nav = useNavigate();
  const ui = useUI();
  const { data: health } = useHealth();
  const { data: me, isLoading: meLoading } = useMe();
  const { data: projects } = useProjects();
  const { data: ws } = useWorkspace();
  const [state, setState] = useState<WizardState>(() => loadState());
  const update = (p: Partial<WizardState>) => setState((s) => ({ ...s, ...p }));
  const skipped = useRef(false);
  useEffect(() => saveState(state), [state]);
  useEffect(() => { document.documentElement.dataset.theme = state.theme; }, [state.theme]);
  useEffect(() => { if (ws && !state.wsName) update({ wsName: ws.onboarded ? ws.name : "", theme: ui.theme, flavor: ws.flavor ?? ui.flavor }); }, [ws]); // eslint-disable-line react-hooks/exhaustive-deps
  // Resume: skip ahead past what's already done (only once, only during first-time setup).
  useEffect(() => {
    if (skipped.current || meLoading || !health || health.onboarded) return;
    skipped.current = true;
    let step = state.step;
    if (me && step < 2) step = 2;
    if (projects?.length) { if (!state.projectId) update({ projectId: projects[0].id }); if (step < 3) step = 3; }
    if (step !== state.step) update({ step });
  }, [me, meLoading, health, projects]); // eslint-disable-line react-hooks/exhaustive-deps

  const go = (step: number) => update({ step: Math.max(0, Math.min(STEPS.length - 1, step)) });
  const finish = () => { celebrate("big"); toast.fun("Welcome to Hyperlane.", "Your assistant is ready whenever you are."); clearState(); ui.setProjectId(state.projectId); nav("/"); };
  const props = { state, update, next: () => go(state.step + 1), back: () => go(state.step - 1) };

  return (
    <div className="min-h-screen grid-bg flex flex-col">
      <div className="hairline" />
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-[360px_1fr] max-w-[1200px] w-full mx-auto p-6 gap-8">
        <aside className="flex flex-col gap-8 lg:sticky lg:top-6 self-start">
          <div className="animate-in">
            <div className="flex items-center gap-3"><span className="w-12 h-12 rounded-[14px] bg-[linear-gradient(135deg,var(--purple),var(--rust))] text-cream inline-flex items-center justify-center font-display font-extrabold text-xl shadow-md animate-float">H</span><div><div className="font-display font-extrabold text-2xl leading-none text-text">Hyperlane</div><div className="text-sm text-text-3 mt-1">Welcome — let's get you set up</div></div></div>
            <p className="mt-4 font-display text-lg leading-snug text-text">Plan, build and ship with an AI analyst on the team.</p>
            <p className="mt-2 text-sm text-text-3">Local-first project management with an AI analyst on the team. Five quick steps; every one can be redone later from Settings.</p>
          </div>
          <ol className="space-y-1" aria-label="Setup progress">
            {STEPS.map((s, i) => { const done = i < state.step; const cur = i === state.step; return (
              <li key={s.key}>
                <button type="button" onClick={() => done && go(i)} disabled={!done && !cur} className={cn("w-full flex items-center gap-3 px-3 h-12 rounded-[10px] text-left transition-colors", cur ? "bg-surface-2 shadow-[inset_2px_0_0_var(--gold)]" : done ? "hover:bg-surface-2/60" : "opacity-50")}>
                  <span className={cn("w-7 h-7 rounded-full grid place-items-center num text-xs font-bold border", done ? "bg-green/15 border-green text-green" : cur ? "border-gold text-gold" : "border-border text-text-3")}>{done ? <Check size={14} /> : i + 1}</span>
                  <span className="flex flex-col leading-tight"><span className={cn("font-display font-semibold", cur && "text-gold")}>{state.flavor ? s.title : s.plain}</span>{state.flavor && <span className="text-[10px] text-text-3">{s.plain}</span>}</span>
                </button>
              </li>
            ); })}
          </ol>
          {health?.onboarded && <button type="button" onClick={() => nav("/")} className="text-xs text-text-3 hover:text-text text-left">← Back to the app (already set up)</button>}
          <p className="text-[11px] text-text-3">Everything stays on this machine. Data lives in <code>./data</code>.</p>
        </aside>
        <main className="panel panel-cut p-6 sm:p-8 animate-pop min-h-[520px]" key={state.step}>
          <div className="hairline mb-6 -mx-6 sm:-mx-8 -mt-6 sm:-mt-8" />
          {state.step === 0 && <StepWorkspace {...props} />}
          {state.step === 1 && <StepProfile {...props} />}
          {state.step === 2 && <StepTemplate {...props} />}
          {state.step === 3 && <StepSeed {...props} />}
          {state.step === 4 && <StepConnect {...props} next={finish} />}
        </main>
      </div>
      <Toaster />
    </div>
  );
}
