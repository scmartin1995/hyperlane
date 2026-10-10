import { RefreshCw, ShieldCheck } from "lucide-react";
import { useAgentStatus } from "@/api/queries";
import { Badge, Button, Skeleton } from "@/components/ui";

const PROVIDERS = [
  { key: "anthropic", title: "Anthropic API", env: "HYPERLANE_LLM_PROVIDER=anthropic\nANTHROPIC_API_KEY=sk-ant-…\nHYPERLANE_LLM_MODEL=claude-sonnet-4-5", note: "Simplest. Usage billed to your Anthropic account." },
  { key: "bedrock", title: "Amazon Bedrock", env: "HYPERLANE_LLM_PROVIDER=bedrock\nAWS_REGION=us-east-1\nAWS_PROFILE=default   # or AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY\nHYPERLANE_LLM_MODEL=anthropic.claude-sonnet-4-5", note: "Keeps traffic inside your AWS account." },
  { key: "claude-code", title: "Claude Code subscription", env: "HYPERLANE_LLM_PROVIDER=claude-code\n# uses the `claude` CLI already logged in on this machine", note: "No API key; uses your existing Claude subscription via the local CLI." },
];

export function AgentTab() {
  const { data: s, isLoading, refetch, isFetching } = useAgentStatus();
  return (
    <div className="space-y-4">
      <section className="panel panel-cut p-4">
        <div className="hairline mb-3" />
        <div className="flex items-start justify-between gap-3">
          <div><div className="eyebrow">Agent status</div>
            {isLoading ? <Skeleton className="h-8 w-64 mt-1" /> : s ? <div className="mt-1"><div className="flex items-center gap-2"><h2 className="text-base">{s.provider || "no provider"} · <span className="num">{s.model || "–"}</span></h2><Badge color={s.available ? "var(--green)" : "var(--rust)"} dot>{s.available ? "connected" : "unavailable"}</Badge></div><p className="text-sm text-text-2 mt-1">{s.detail}</p></div> : <p className="text-sm text-text-3 mt-1">Status endpoint not reachable.</p>}
          </div>
          <Button size="sm" variant="ghost" icon={RefreshCw} loading={isFetching} onClick={() => refetch()}>Re-check</Button>
        </div>
      </section>
      <div className="grid gap-3 md:grid-cols-3">
        {PROVIDERS.map((p) => (
          <section key={p.key} className={`panel p-4 ${s?.provider === p.key ? "border-gold" : ""}`}>
            <div className="eyebrow">{s?.provider === p.key ? "Current" : "Option"}</div><h3 className="font-display font-bold">{p.title}</h3>
            <p className="text-xs text-text-3 mt-1 mb-2">{p.note}</p>
            <pre className="text-[11px] bg-surface-3 rounded-[8px] p-2.5 overflow-auto whitespace-pre-wrap">{p.env}</pre>
          </section>
        ))}
      </div>
      <section className="panel p-4 text-sm">
        <div className="eyebrow">How to switch</div>
        <ol className="list-decimal pl-5 mt-1 space-y-1 text-text-2"><li>Edit <code>.env</code> in the Hyperlane folder (next to <code>pyproject.toml</code>). Secrets are never stored in the database.</li><li>Restart the server (<code>./hyperlane</code>).</li><li>Come back here and hit Re-check.</li></ol>
        <div className="mt-3 flex items-start gap-2 p-3 rounded-[8px] border border-border bg-surface-2/60"><ShieldCheck size={16} className="text-green shrink-0 mt-0.5" /><p className="text-xs text-text-2"><b>Privacy.</b> The only things that leave this machine are the prompts sent to the provider you choose (item titles, descriptions, metrics the agent reads) and messages you explicitly route to Slack, Teams or email. Private action items are never sent to anyone but you.</p></div>
      </section>
    </div>
  );
}
