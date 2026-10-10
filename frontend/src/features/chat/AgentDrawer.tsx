// Placeholder: the chat feature replaces this with the real agent drawer.
import { Drawer, EmptyState } from "@/components/ui";
import { useUI, label } from "@/lib/store";

export function AgentDrawer() {
  const ui = useUI();
  return (
    <Drawer open={ui.agentOpen} onClose={() => ui.setAgentOpen(false)} title={label("agent", ui.flavor)} eyebrow="Agent" width={560}>
      <div className="p-4"><EmptyState icon="✨" title="The agent is warming up" body="This drawer will host the business-analyst chat." /></div>
    </Drawer>
  );
}
