// Side drawer wrapper around ItemDetail; board/backlog use this. Keeps a tiny history so child links don't dead-end.
import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { Drawer, IconButton } from "@/components/ui";
import { ItemDetail } from "./ItemDetail";

export function ItemDrawer({ id, onClose }: { id: string | null; onClose: () => void }) {
  const [stack, setStack] = useState<string[]>([]);
  useEffect(() => { setStack(id ? [id] : []); }, [id]);
  const current = stack[stack.length - 1] ?? null;
  return (
    <Drawer open={!!current} onClose={onClose} width={640} eyebrow="Work item" title={current ? "Details" : ""}
      actions={stack.length > 1 ? <IconButton icon={ArrowLeft} label="Back" onClick={() => setStack((s) => s.slice(0, -1))} /> : undefined}>
      {current && <ItemDetail id={current} compact onOpenItem={(next) => setStack((s) => [...s, next])} onArchived={onClose} />}
    </Drawer>
  );
}
