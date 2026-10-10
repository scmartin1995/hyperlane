// The Assistant drawer (rendered by AppShell). Same ChatView as /chat, narrower.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Maximize2, Plus } from "lucide-react";
import { Drawer, IconButton } from "@/components/ui";
import { useUI, label } from "@/lib/store";
import { ChatView } from "./ChatView";

export function AgentDrawer() {
  const ui = useUI();
  const nav = useNavigate();
  const [threadId, setThreadId] = useState<string | null>(null);
  return (
    <Drawer open={ui.agentOpen} onClose={() => ui.setAgentOpen(false)} title={label("agent", ui.flavor)} eyebrow="Agent · business analyst" width={560}
      actions={<><IconButton icon={Plus} label="New thread" onClick={() => setThreadId(null)} /><IconButton icon={Maximize2} label="Open full page" onClick={() => { ui.setAgentOpen(false); nav(threadId ? `/chat/${threadId}` : "/chat"); }} /></>}>
      <ChatView compact threadId={threadId} onThreadCreated={(t) => setThreadId(t.id)} />
    </Drawer>
  );
}
