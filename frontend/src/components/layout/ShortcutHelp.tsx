import { create } from "zustand";
import { Kbd, Modal } from "@/components/ui";

interface S { open: boolean; set: (o: boolean) => void; toggle: () => void }
export const useShortcutHelp = create<S>((set) => ({ open: false, set: (open) => set({ open }), toggle: () => set((s) => ({ open: !s.open })) }));

const GROUPS: { title: string; rows: [string[], string][] }[] = [
  { title: "Anywhere", rows: [[["Ctrl", "K"], "Search or jump anywhere"], [["/"], "Open the assistant"], [["?"], "This cheatsheet"], [["Esc"], "Close drawer / modal"]] },
  { title: "Go to", rows: [[["g", "h"], "Home"], [["g", "b"], "Board"], [["g", "l"], "Backlog"], [["g", "s"], "Sprints"], [["g", "r"], "Insights"], [["g", "i"], "Inbox"], [["g", "a"], "My tasks"], [["g", "p"], "Team"]] },
  { title: "Work items", rows: [[["c"], "Create item"], [["e"], "Edit description"], [["Ctrl", "Enter"], "Save / send"], [["Enter"], "Chain-create next item"]] },
];

export function ShortcutHelp() {
  const { open, set } = useShortcutHelp();
  return (
    <Modal open={open} onClose={() => set(false)} title="Keyboard shortcuts" eyebrow="Keyboard" width={620}>
      <div className="grid sm:grid-cols-3 gap-5 py-2">
        {GROUPS.map((g) => (
          <div key={g.title}>
            <div className="eyebrow mb-2">{g.title}</div>
            <ul className="space-y-1.5">
              {g.rows.map(([keys, label]) => (
                <li key={label} className="flex items-center justify-between gap-3 text-sm">
                  <span className="text-text-2">{label}</span>
                  <span className="flex gap-1">{keys.map((k) => <Kbd key={k}>{k}</Kbd>)}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-text-3 mt-3">Shortcuts are shown next to commands in the palette so you pick them up as you go.</p>
    </Modal>
  );
}
