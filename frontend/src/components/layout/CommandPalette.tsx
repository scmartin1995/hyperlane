import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { create } from "zustand";
import { api } from "@/api/client";
import type { WorkItem } from "@/api/types";
import { useUI, label } from "@/lib/store";
import { Kbd, cn } from "@/components/ui";

interface PaletteState { open: boolean; toggle: () => void; set: (o: boolean) => void }
export const useCommandPalette = create<PaletteState>((set) => ({ open: false, toggle: () => set((s) => ({ open: !s.open })), set: (open) => set({ open }) }));

export function CommandPalette() {
  const { open, set } = useCommandPalette();
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);
  const nav = useNavigate();
  const ui = useUI();
  const { data: results } = useQuery({ queryKey: ["search", q], queryFn: () => api.get<WorkItem[]>(`/search?q=${encodeURIComponent(q)}`), enabled: open && q.trim().length >= 2 });

  const commands = useMemo(() => [
    { id: "home", label: `${label("home", ui.flavor)}`, hint: "Go", run: () => nav("/") },
    { id: "board", label: `${label("board", ui.flavor)} · Board`, hint: "Go", run: () => nav("/board") },
    { id: "backlog", label: `${label("backlog", ui.flavor)} · Backlog`, hint: "Go", run: () => nav("/backlog") },
    { id: "sprints", label: `${label("sprints", ui.flavor)} · Sprints`, hint: "Go", run: () => nav("/sprints") },
    { id: "reports", label: `${label("reports", ui.flavor)} · Reports`, hint: "Go", run: () => nav("/reports") },
    { id: "intake", label: `${label("intake", ui.flavor)} · Intake`, hint: "Go", run: () => nav("/intake") },
    { id: "actions", label: `${label("actionItems", ui.flavor)} · Action items`, hint: "Go", run: () => nav("/action-items") },
    { id: "people", label: `${label("people", ui.flavor)} · People`, hint: "Go", run: () => nav("/people") },
    { id: "settings", label: `${label("settings", ui.flavor)} · Settings`, hint: "Go", run: () => nav("/settings") },
    { id: "agent", label: "Open the assistant", hint: "/", run: () => ui.setAgentOpen(true) },
    { id: "new-item", label: "New work item", hint: "c", run: () => nav("/backlog?new=1") },
    { id: "theme", label: "Toggle theme", hint: "", run: () => ui.setTheme(ui.theme === "dark" ? "light" : "dark") },
      ].filter((c) => !q || c.label.toLowerCase().includes(q.toLowerCase())), [q, ui, nav]);

  const rows = useMemo(() => [
    ...(results ?? []).map((it) => ({ id: it.id, label: `${it.key} · ${it.title}`, hint: it.status, run: () => nav(`/items/${it.id}`) })),
    ...commands,
  ], [results, commands, nav]);

  useEffect(() => { if (!open) { setQ(""); setIdx(0); } }, [open]);
  useEffect(() => setIdx(0), [q]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[55] bg-black/60 backdrop-blur-[2px] flex items-start justify-center pt-[12vh] p-4 animate-in" onMouseDown={(e) => e.target === e.currentTarget && set(false)}>
      <div className="panel panel-cut w-full max-w-[600px] animate-pop overflow-hidden">
        <div className="hairline" />
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search items, jump anywhere, run a command…" className="w-full h-12 px-4 bg-transparent outline-none text-base"
          onKeyDown={(e) => { if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(rows.length - 1, i + 1)); } if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(0, i - 1)); } if (e.key === "Enter" && rows[idx]) { rows[idx].run(); set(false); } if (e.key === "Escape") set(false); }} />
        <div className="max-h-[50vh] overflow-y-auto border-t border-border p-1">
          {rows.length === 0 && <div className="p-4 text-sm text-text-3">Nothing matches.</div>}
          {rows.map((r, i) => (
            <button key={r.id} onMouseEnter={() => setIdx(i)} onClick={() => { r.run(); set(false); }} className={cn("w-full flex items-center justify-between px-3 h-9 rounded-[6px] text-sm text-left", i === idx ? "bg-purple-tint text-purple dark:text-gold" : "text-text-2")}>
              <span className="truncate">{r.label}</span>{r.hint && <Kbd>{r.hint}</Kbd>}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
