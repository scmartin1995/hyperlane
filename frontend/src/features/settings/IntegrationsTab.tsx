import { Hash, Mail, MessageSquare, Zap } from "lucide-react";
import { useIntegrationsStatus } from "@/api/queries";
import { fmtDateTime } from "@/lib/format";
import { Badge, Button, Skeleton, toast } from "@/components/ui";
import { useNotificationLog, useTestIntegration } from "./hooks";
import { EmailRouting } from "./EmailRouting";

export function IntegrationsTab() {
  const { data: s, isLoading } = useIntegrationsStatus();
  const log = useNotificationLog();
  const test = useTestIntegration();
  const run = (kind: "slack" | "teams" | "email") => test.mutate(kind, { onSuccess: (r) => (r.ok ? toast.success(`${kind} works`, r.detail) : toast.error(`${kind} test failed`, r.detail)), onError: (e) => toast.error(`${kind} test failed`, (e as Error).message) });
  const cards = s ? [
    { kind: "slack" as const, icon: Hash, title: "Slack", enabled: s.slack.enabled, detail: `${s.slack.detail}${s.slack.channel ? ` · #${s.slack.channel}` : ""}`, extra: s.slack.connected ? "socket connected" : s.slack.enabled ? "not connected" : undefined },
    { kind: "teams" as const, icon: MessageSquare, title: "Microsoft Teams", enabled: s.teams.enabled, detail: s.teams.detail },
    { kind: "email" as const, icon: Mail, title: "Email connector", enabled: s.email.enabled, detail: `${s.email.detail} New mail becomes backlog items needing triage; the assistant asks follow-up questions by reply.`, extra: s.email.last_poll ? `last poll ${fmtDateTime(s.email.last_poll)}` : undefined },
  ] : [];
  return (
    <div className="space-y-4">
      <div className="grid gap-3 md:grid-cols-3">
        {isLoading ? [0, 1, 2].map((i) => <Skeleton key={i} className="h-36" />) : cards.map((c) => (
          <section key={c.kind} className="panel p-4 flex flex-col">
            <div className="flex items-center justify-between"><h3 className="font-display font-bold inline-flex items-center gap-2"><c.icon size={16} /> {c.title}</h3><Badge color={c.enabled ? "var(--green)" : "var(--smoke)"} dot>{c.enabled ? "enabled" : "off"}</Badge></div>
            <p className="text-xs text-text-3 mt-1 flex-1">{c.detail}{c.extra && <> · {c.extra}</>}</p>
            <Button size="sm" variant="outline" icon={Zap} className="mt-3 self-start" disabled={!c.enabled} loading={test.isPending && test.variables === c.kind} onClick={() => run(c.kind)}>Send test</Button>
          </section>
        ))}
      </div>
      <EmailRouting />
      <p className="text-xs text-text-3">Configure with env vars in <code>.env</code> — see <code>docs/INTEGRATIONS.md</code> in the Hyperlane folder. Nothing is sent anywhere unless the matching variables are set.</p>
      <section className="panel overflow-hidden">
        <header className="px-4 pt-4 pb-2"><div className="eyebrow">Notification log</div><h2 className="text-base">Everything that went out</h2></header>
        {log.isLoading ? <div className="p-4"><Skeleton className="h-20" /></div> : !log.data?.length ? <p className="px-4 pb-4 text-sm text-text-3">Nothing sent yet.</p> : (
          <table className="w-full text-xs"><thead><tr className="text-left border-y border-border bg-surface-2/50"><th className="px-4 py-2 eyebrow">When</th><th className="px-2 py-2 eyebrow">Channel</th><th className="px-2 py-2 eyebrow">Kind</th><th className="px-2 py-2 eyebrow">Target</th><th className="px-2 py-2 eyebrow">Body</th><th className="px-4 py-2 eyebrow">OK</th></tr></thead>
            <tbody>{log.data.map((n) => <tr key={n.id} className="border-b border-border"><td className="px-4 py-1.5 whitespace-nowrap">{fmtDateTime(n.created_at)}</td><td className="px-2 py-1.5">{n.channel}</td><td className="px-2 py-1.5">{n.kind}</td><td className="px-2 py-1.5 num">{n.target ?? "–"}</td><td className="px-2 py-1.5 max-w-[360px] truncate" title={n.body}>{n.body}</td><td className="px-4 py-1.5">{n.ok ? <span className="text-green">✓</span> : <span className="text-rust-light" title={n.error ?? ""}>✗</span>}</td></tr>)}</tbody></table>
        )}
      </section>
    </div>
  );
}
