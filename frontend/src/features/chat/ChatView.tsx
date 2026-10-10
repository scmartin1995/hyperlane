// Shared chat surface for the assistant drawer and the /chat page. Streams via SSE.
import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronRight, Send, Square, Wrench, AlertTriangle, Sparkles, X } from "lucide-react";
import { streamPost } from "@/api/client";
import { qk, useAgentStatus, useProject } from "@/api/queries";
import type { ChatMessage, ChatStreamEvent, ChatThread } from "@/api/types";
import { useUI } from "@/lib/store";
import { Badge, Button, IconButton, Markdown, Select, Spinner, cn, toast } from "@/components/ui";
import { MODES, type Mode, useThread, useThreadMutations } from "./hooks";

const SUGGESTIONS = ["Draft stories for an onboarding epic", "How is the sprint tracking?", "What should we pull into next sprint?", "Summarize what changed this week", "Add an action item for me to…"];

type ToolChip = { id: string; name: string; input: unknown; ok?: boolean; summary?: string };
type Live = { text: string; tools: ToolChip[]; error?: string } | null;

let consumedPrefill: unknown = null;
const stripContext = (t: string) => t.replace(/^\[context:[^\]]*\]\n?/, "");

export function ChatView({ threadId, onThreadCreated, compact }: { threadId: string | null; onThreadCreated: (t: ChatThread) => void; compact?: boolean }) {
  const ui = useUI();
  const qc = useQueryClient();
  const { data: status } = useAgentStatus();
  const { data: project } = useProject(ui.projectId ?? undefined);
  const { data: thread, isLoading } = useThread(threadId);
  const { create } = useThreadMutations();
  const [mode, setMode] = useState<Mode>("analyst");
  const [input, setInput] = useState("");
  const [live, setLive] = useState<Live>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [ctx, setCtx] = useState<Record<string, unknown>>({});
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const ta = useRef<HTMLTextAreaElement>(null);
  const streaming = !!live;
  useEffect(() => {
    const { prefill, nonce, ...rest } = (ui.agentContext ?? {}) as Record<string, unknown>;
    setCtx(rest);
    if (typeof prefill === "string" && prefill.trim() && nonce !== consumedPrefill) {
      consumedPrefill = nonce;  // module-level guard: the drawer and the full page may both be mounted
      setTimeout(() => void sendRef.current?.(prefill), 50);
    }
  }, [ui.agentContext]);
  const sendRef = useRef<((raw?: string) => Promise<void>) | null>(null);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [thread?.messages?.length, live?.text, pending]);
  useEffect(() => () => abort.current?.abort(), []);

  const contextChips = Object.entries(ctx).filter(([k, v]) => v != null && (k.endsWith("_id") || k.endsWith("_name") || k === "picked") && typeof v !== "object").map(([k, v]) => [k, String(v)] as const);
  const contextPrefix = () => { const ids = Object.entries(ctx).filter(([k, v]) => k.endsWith("_id") && v).map(([k, v]) => `${k}=${String(v)}`); return ids.length ? `[context: ${ids.join(", ")}]\n` : ""; };

  const send = useCallback(async (raw?: string) => {
    const content = (raw ?? input).trim(); if (!content || streaming) return;
    let tid = threadId;
    try {
      if (!tid) { const t = await create.mutateAsync({ project_id: ui.projectId, mode, context: ctx, title: content.slice(0, 60) }); tid = t.id; onThreadCreated(t); }
    } catch (e) { toast.error("Couldn't start a thread", (e as Error).message); return; }
    setInput(""); setPending(content); setLive({ text: "", tools: [] });
    const ac = new AbortController(); abort.current = ac;
    try {
      await streamPost<ChatStreamEvent>(`/chat/threads/${tid}/messages`, { content: contextPrefix() + content }, (ev) => {
        setLive((l) => {
          if (!l) return l;
          switch (ev.type) {
            case "text": return { ...l, text: l.text + ev.delta };
            case "tool_call": return { ...l, tools: [...l.tools, { id: ev.id, name: ev.name, input: ev.input }] };
            case "tool_result": return { ...l, tools: l.tools.map((t) => (t.id === ev.id ? { ...t, ok: ev.ok, summary: ev.summary } : t)) };
            case "error": return { ...l, error: ev.error };
            case "message": return { ...l, text: ev.message.content || l.text };
            default: return l;
          }
        });
      }, ac.signal);
    } catch (e) {
      if ((e as Error).name !== "AbortError") { setLive((l) => (l ? { ...l, error: (e as Error).message } : l)); toast.error("The assistant dropped the connection", (e as Error).message); }
    } finally {
      await qc.invalidateQueries({ queryKey: qk.chatThread(tid!) }); qc.invalidateQueries({ queryKey: qk.chatThreads });
      qc.invalidateQueries({ queryKey: ["items"] }); qc.invalidateQueries({ queryKey: ["action-items"] });
      setLive(null); setPending(null); abort.current = null;
    }
  }, [input, streaming, threadId, create, ui.projectId, mode, ctx, onThreadCreated, qc]); // eslint-disable-line react-hooks/exhaustive-deps

  sendRef.current = send;
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); } };
  const messages = thread?.messages ?? [];
  const empty = !threadId || (!isLoading && messages.length === 0 && !pending);

  return (
    <div className="flex flex-col h-full min-h-0">
      {status && !status.available && (
        <div className="m-3 mb-0 p-2.5 rounded-[8px] border border-gold/40 bg-gold/10 text-xs flex items-start gap-2"><AlertTriangle size={14} className="text-gold shrink-0 mt-0.5" /><span><b>The assistant isn't connected.</b> {status.detail} <Link to="/settings/agent">Configure a provider →</Link></span></div>
      )}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
        {isLoading && threadId && <div className="flex justify-center py-6"><Spinner /></div>}
        {empty && !isLoading && (
          <div className="py-6 text-center animate-in">
            <div className="text-3xl mb-2">✨</div>
            <h3 className="font-display font-bold">Your assistant is ready</h3>
            <p className="text-xs text-text-3 mt-1 mb-4">Asks the right questions, reads the board, writes the backlog. {project ? `Scoped to ${project.name}.` : "Pick a project to scope it."}</p>
            {!threadId && <div className="flex justify-center mb-4"><Select className="!w-auto h-8 text-xs" value={mode} onChange={(e) => setMode(e.target.value as Mode)} aria-label="Mode">{MODES.map((m) => <option key={m.key} value={m.key}>{m.label} — {m.hint}</option>)}</Select></div>}
            <div className={cn("grid gap-1.5", compact ? "grid-cols-1" : "sm:grid-cols-2 max-w-xl mx-auto")}>{SUGGESTIONS.map((s) => <button key={s} onClick={() => (s.endsWith("…") ? (setInput(s.slice(0, -1)), ta.current?.focus()) : void send(s))} className="text-left text-xs px-3 py-2 rounded-[8px] border border-border bg-surface-2/60 hover:border-purple hover:bg-purple-tint transition-colors">{s}</button>)}</div>
          </div>
        )}
        {messages.map((m) => <MessageBubble key={m.id} msg={m} />)}
        {pending && !(messages.length > 0 && messages[messages.length - 1].role === "user" && stripContext(messages[messages.length - 1].content) === pending) && <UserBubble text={pending} />}
        {live && (
          <div className="flex justify-start"><div className="max-w-[92%] rounded-[12px] px-3 py-2 bg-surface-2 border border-border animate-in">
            <div className="text-[10px] text-text-3 font-display font-semibold mb-1 inline-flex items-center gap-1"><Sparkles size={10} /> Assistant {!live.text && live.tools.length === 0 && <Spinner size={10} />}</div>
            {live.tools.map((t) => <ToolChipView key={t.id} tool={t} />)}
            {live.text && <Markdown>{live.text}</Markdown>}
            {!live.text && live.tools.length === 0 && <div className="flex gap-1 py-1"><Dot /><Dot d={0.15} /><Dot d={0.3} /></div>}
            {live.error && <div className="text-xs text-rust-light mt-1">⚠ {live.error}</div>}
          </div></div>
        )}
        <div ref={bottom} />
      </div>
      <div className="border-t border-border p-2.5 bg-surface/80">
        {contextChips.length > 0 && <div className="flex flex-wrap gap-1 mb-1.5">{contextChips.map(([k, v]) => <Badge key={k} size="xs" color="var(--teal)">{k.replace(/_id$|_name$/, "")}: {v.length > 24 ? v.slice(0, 24) + "…" : v}<button onClick={() => setCtx((c) => { const n = { ...c }; delete n[k]; return n; })} aria-label="Remove context"><X size={10} /></button></Badge>)}</div>}
        <div className="flex items-end gap-2">
          <textarea ref={ta} value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={onKey} rows={compact ? 2 : 3} placeholder={streaming ? "Thinking…" : "Ask anything about this project… (Enter to send, Shift+Enter for a new line)"} disabled={streaming} className="flex-1 bg-surface-2 border border-border rounded-[8px] px-3 py-2 text-sm placeholder:text-text-3 focus:border-teal focus:outline-none resize-none disabled:opacity-60" aria-label="Message" />
          {streaming ? <IconButton icon={Square} label="Stop" size="md" className="bg-rust/20 text-rust-light" onClick={() => abort.current?.abort()} /> : <Button variant="teal" size="md" icon={Send} onClick={() => void send()} disabled={!input.trim()} aria-label="Send">Send</Button>}
        </div>
      </div>
    </div>
  );
}

const Dot = ({ d = 0 }: { d?: number }) => <span className="w-1.5 h-1.5 rounded-full bg-text-3 animate-bounce" style={{ animationDelay: `${d}s` }} />;

function UserBubble({ text }: { text: string }) { return <div className="flex justify-end"><div className="max-w-[85%] rounded-[12px] px-3 py-2 bg-purple-tint border border-purple/20 text-sm whitespace-pre-wrap animate-in">{text.replace(/^\[context:[^\]]*\]\n/, "")}</div></div>; }

export function MessageBubble({ msg }: { msg: ChatMessage }) {
  if (msg.role === "user") return <UserBubble text={msg.content} />;
  if (msg.role === "tool") return <div className="flex justify-start"><div className="text-[11px] text-text-3 px-2 inline-flex items-center gap-1"><Wrench size={10} /> {msg.content.slice(0, 120)}</div></div>;
  return (
    <div className="flex justify-start"><div className="max-w-[92%] rounded-[12px] px-3 py-2 bg-surface-2 border border-border animate-in">
      <div className="text-[10px] text-text-3 font-display font-semibold mb-1 inline-flex items-center gap-1"><Sparkles size={10} /> Assistant</div>
      {msg.tool_calls?.map((t, i) => <ToolChipView key={i} tool={{ id: String(i), name: t.name, input: t.input, ok: true, summary: t.result_summary }} />)}
      <Markdown>{msg.content}</Markdown>
    </div></div>
  );
}

function ToolChipView({ tool }: { tool: ToolChip }) {
  const [open, setOpen] = useState(false);
  const verb = tool.name.replace(/_/g, " ");
  return (
    <div className="mb-1">
      <button onClick={() => setOpen((o) => !o)} className={cn("inline-flex items-center gap-1 text-[11px] px-2 h-5 rounded-full border", tool.ok === false ? "border-rust/50 text-rust-light" : tool.ok ? "border-green/40 text-text-2" : "border-teal/40 text-teal animate-pulse")}>
        <Wrench size={10} /> {tool.ok === undefined ? `${verb}…` : verb}{tool.ok === false && " · failed"}{open ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
      </button>
      {open && <pre className="mt-1 text-[10px] bg-surface-3 rounded p-2 overflow-auto max-h-40">{tool.summary ? `→ ${tool.summary}\n` : ""}{JSON.stringify(tool.input, null, 1)}</pre>}
    </div>
  );
}
