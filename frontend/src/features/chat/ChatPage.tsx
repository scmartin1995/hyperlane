// /chat and /chat/:id — the assistant, full width, with a threads sidebar.
import { useNavigate, useParams } from "react-router-dom";
import { Plus, Trash2, MessageSquare } from "lucide-react";
import { useProjects } from "@/api/queries";
import { useUI, label } from "@/lib/store";
import { ago } from "@/lib/format";
import { Badge, Button, IconButton, PageHeader, Skeleton, cn, toast } from "@/components/ui";
import { ChatView } from "./ChatView";
import { MODES, useThreadMutations, useThreads } from "./hooks";

export default function ChatPage() {
  const { id } = useParams<{ id?: string }>();
  const nav = useNavigate();
  const ui = useUI();
  const { data: threads, isLoading } = useThreads();
  const { data: projects } = useProjects();
  const { remove } = useThreadMutations();
  const mine = (threads ?? []).filter((t) => !ui.projectId || !t.project_id || t.project_id === ui.projectId);
  return (
    <div className="h-[calc(100vh-7.5rem)] flex flex-col">
      <PageHeader eyebrow="Agent · business analyst" title={label("agent", ui.flavor)} subtitle="Threads are yours; the assistant only acts through the same API you use." actions={<Button variant="primary" icon={Plus} onClick={() => nav("/chat")}>New thread</Button>} />
      <div className="flex-1 min-h-0 grid grid-cols-[260px_1fr] gap-3">
        <aside className="panel overflow-y-auto p-1.5">
          {isLoading ? <div className="space-y-1 p-1">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div> : mine.length === 0 ? <p className="text-xs text-text-3 p-3">No threads yet. Ask something to start one.</p> : mine.map((t) => {
            const p = projects?.find((x) => x.id === t.project_id); const m = MODES.find((x) => x.key === t.mode);
            return (
              <div key={t.id} className={cn("group flex items-start gap-1 rounded-[8px] px-2 py-1.5 hover:bg-surface-2", t.id === id && "bg-surface-2 text-gold")}>
                <button onClick={() => nav(`/chat/${t.id}`)} className="flex-1 min-w-0 text-left">
                  <div className="text-sm truncate inline-flex items-center gap-1"><MessageSquare size={11} className="shrink-0" /> {t.title || "Untitled"}</div>
                  <div className="text-[10px] text-text-3 flex items-center gap-1">{m && <Badge size="xs">{m.label}</Badge>}{p && <span>{p.key}</span>}<span>· {ago(t.updated_at)}</span></div>
                </button>
                <IconButton icon={Trash2} label="Delete thread" size="xs" className="opacity-0 group-hover:opacity-100" onClick={() => { if (confirm("Delete this thread?")) remove.mutate(t.id, { onSuccess: () => { if (t.id === id) nav("/chat"); }, onError: (e) => toast.error("Couldn't delete", (e as Error).message) }); }} />
              </div>
            );
          })}
        </aside>
        <section className="panel panel-cut overflow-hidden flex flex-col min-h-0"><div className="hairline" /><ChatView threadId={id ?? null} onThreadCreated={(t) => nav(`/chat/${t.id}`, { replace: true })} /></section>
      </div>
    </div>
  );
}
