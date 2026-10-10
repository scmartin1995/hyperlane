import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Flag, Check, Minus, RefreshCw } from "lucide-react";
import { api } from "@/api/client";
import { useHealth } from "@/api/queries";
import type { Workspace } from "@/api/types";
import { Button, Skeleton, cn } from "@/components/ui";
import type { StepProps } from "../state";

export function StepConnect({ state, back, next }: StepProps & { next: () => void }) {
  const { data: health, isLoading, refetch, isFetching } = useHealth();
  const qc = useQueryClient();
  const finish = useMutation({
    mutationFn: () => api.patch<Workspace>("/workspace", { onboarded: true, name: state.wsName.trim() || undefined, theme: state.theme, flavor: state.flavor }),
    onSuccess: async () => { await qc.invalidateQueries(); next(); },
  });
  const rows = health ? [
    { name: "Claude agent", ok: health.llm.configured, detail: health.llm.configured ? `${health.llm.provider} · ${health.llm.model}` : "Set ANTHROPIC_API_KEY (or Bedrock / Claude Code) in .env", vars: "ANTHROPIC_API_KEY / HL_LLM_PROVIDER" },
    { name: "Slack", ok: health.slack, detail: health.slack ? "Socket Mode connected" : "Threads, /hyperlane commands and digests", vars: "SLACK_BOT_TOKEN, SLACK_APP_TOKEN" },
    { name: "Microsoft Teams", ok: health.teams, detail: health.teams ? "Webhook configured" : "Notifications via incoming webhook", vars: "TEAMS_WEBHOOK_URL" },
    { name: "Email intake", ok: health.email_intake, detail: health.email_intake ? "IMAP polling" : "Turn an inbox into requests the agent triages", vars: "IMAP_HOST, IMAP_USER, IMAP_PASSWORD, SMTP_*" },
  ] : [];
  return (
    <div className="space-y-5">
      <div><div className="eyebrow">Step 5 · Connect</div><h2 className="text-2xl mt-1">Open comms</h2><p className="text-text-3 text-sm mt-1">Integrations are optional and all off by default. Nothing leaves this machine unless you flip one on.</p></div>
      {isLoading ? <div className="space-y-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}</div> : (
        <ul className="panel divide-y divide-border">
          {rows.map((r) => (
            <li key={r.name} className="flex items-center gap-3 px-4 py-3">
              <span className={cn("w-7 h-7 rounded-full grid place-items-center border", r.ok ? "border-green text-green bg-green/10" : "border-border text-text-3")}>{r.ok ? <Check size={14} /> : <Minus size={14} />}</span>
              <div className="flex-1 min-w-0"><div className="font-display font-semibold text-sm">{r.name} <span className={cn("text-[10px] uppercase tracking-wider ml-1", r.ok ? "text-green" : "text-text-3")}>{r.ok ? "connected" : "off"}</span></div><div className="text-xs text-text-3 truncate">{r.detail}</div></div>
              {!r.ok && <code className="text-[10px] text-text-3 hidden sm:block">{r.vars}</code>}
            </li>
          ))}
        </ul>
      )}
      <div className="panel p-4 text-sm text-text-2 space-y-1">
        <p>To connect something: add the variables to <code>.env</code> next to the launcher, then restart <code>./hyperlane</code>. Full walkthrough in <code>docs/INTEGRATIONS.md</code>.</p>
        <p className="text-xs text-text-3">Changed .env already? <button type="button" className="underline inline-flex items-center gap-1" onClick={() => refetch()}><RefreshCw size={11} className={cn(isFetching && "animate-spin")} /> Re-check</button></p>
      </div>
      <div className="flex justify-between"><Button variant="ghost" icon={ArrowLeft} onClick={back}>Back</Button><Button variant="primary" size="lg" icon={Flag} loading={finish.isPending} onClick={() => finish.mutate()}>Lights out — let's go</Button></div>
    </div>
  );
}
