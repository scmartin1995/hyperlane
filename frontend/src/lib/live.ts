// Subscribe to the server's SSE stream and invalidate queries so every open browser stays in sync.
import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { LiveEvent } from "@/api/types";

type Listener = (e: LiveEvent) => void;
const listeners = new Set<Listener>();
export function onLiveEvent(fn: Listener) { listeners.add(fn); return () => { listeners.delete(fn); }; }

export function useLiveEvents() {
  const qc = useQueryClient();
  useEffect(() => {
    let es: EventSource | null = null;
    let retry = 1000;
    const connect = () => {
      es = new EventSource("/api/events");
      es.onopen = () => { retry = 1000; };
      es.onerror = () => { es?.close(); setTimeout(connect, (retry = Math.min(retry * 2, 15000))); };
      const handle = (ev: MessageEvent) => {
        let e: LiveEvent;
        try { e = JSON.parse(ev.data); } catch { return; }
        listeners.forEach((l) => l(e));
        const t = e.type;
        if (t.startsWith("work_item") || t.startsWith("comment")) {
          qc.invalidateQueries({ queryKey: ["items"] }); qc.invalidateQueries({ queryKey: ["item"] });
          qc.invalidateQueries({ queryKey: ["project"] }); qc.invalidateQueries({ queryKey: ["metrics"] }); qc.invalidateQueries({ queryKey: ["activity"] });
        } else if (t.startsWith("sprint")) {
          qc.invalidateQueries({ queryKey: ["sprints"] }); qc.invalidateQueries({ queryKey: ["sprint"] }); qc.invalidateQueries({ queryKey: ["items"] });
          qc.invalidateQueries({ queryKey: ["project"] }); qk(qc, "metrics"); qk(qc, "plan-suggest"); qk(qc, "sprint-capacity"); qk(qc, "retro");
        } else if (t.startsWith("project")) { qc.invalidateQueries({ queryKey: ["projects"] }); qc.invalidateQueries({ queryKey: ["project"] }); }
        else if (t.startsWith("user")) { qc.invalidateQueries({ queryKey: ["users"] }); qc.invalidateQueries({ queryKey: ["profiles"] }); }
        else if (t.startsWith("action_item")) qc.invalidateQueries({ queryKey: ["action-items"] });
        else if (t.startsWith("intake")) qc.invalidateQueries({ queryKey: ["intake"] });
        else if (t.startsWith("workspace")) qc.invalidateQueries({ queryKey: ["workspace"] });
        else if (t.startsWith("evm")) qc.invalidateQueries({ queryKey: ["evm"] });
        else if (t.startsWith("capacity") || t.startsWith("retro")) { qk(qc, "capacity"); qk(qc, "sprint-capacity"); qk(qc, "retro"); }
      };
      // every event type is sent with its own event name; listen generically via onmessage won't fire, so:
      const known = ["work_item.created","work_item.updated","work_item.moved","work_item.deleted","comment.created","comment.updated","comment.deleted",
        "sprint.created","sprint.updated","sprint.started","sprint.closed","project.created","project.updated","project.deleted","user.created","user.updated",
        "action_item.created","action_item.updated","action_item.deleted","intake.created","intake.updated","workspace.updated","evm.snapshot","capacity.updated","retro.updated","chat.message","notification.sent"];
      known.forEach((k) => es!.addEventListener(k, handle as EventListener));
    };
    connect();
    return () => es?.close();
  }, [qc]);
}
function qk(qc: ReturnType<typeof useQueryClient>, key: string) { qc.invalidateQueries({ queryKey: [key] }); }
