import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UIState {
  theme: "dark" | "light";
  flavor: boolean; // racing-flavored copy
  projectId: string | null;
  sidebarCollapsed: boolean;
  agentOpen: boolean;
  agentContext: Record<string, unknown>;
  soundOn: boolean;
  setTheme: (t: "dark" | "light") => void;
  setFlavor: (f: boolean) => void;
  setProjectId: (id: string | null) => void;
  toggleSidebar: () => void;
  setAgentOpen: (open: boolean, context?: Record<string, unknown>) => void;
  setSoundOn: (on: boolean) => void;
}

export const useUI = create<UIState>()(
  persist(
    (set) => ({
      theme: "light",
      flavor: false,
      projectId: null,
      sidebarCollapsed: false,
      agentOpen: false,
      agentContext: {},
      soundOn: false,
      setTheme: (theme) => { document.documentElement.dataset.theme = theme; set({ theme }); },
      setFlavor: (flavor) => set({ flavor }),
      setProjectId: (projectId) => set({ projectId }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setAgentOpen: (agentOpen, context) => set((s) => ({ agentOpen, agentContext: context ?? s.agentContext })),
      setSoundOn: (soundOn) => set({ soundOn }),
    }),
    { name: "hyperlane-ui-v2", partialize: (s) => ({ theme: s.theme, flavor: s.flavor, projectId: s.projectId, sidebarCollapsed: s.sidebarCollapsed, soundOn: s.soundOn }) },
  ),
);

/** Navigation labels. `flavor` is kept for compatibility; both variants now use plain product language. */
export const LABELS = {
  home: { fun: "Home", plain: "Home" },
  board: { fun: "Board", plain: "Board" },
  backlog: { fun: "Backlog", plain: "Backlog" },
  sprints: { fun: "Sprints", plain: "Sprints" },
  reports: { fun: "Insights", plain: "Insights" },
  intake: { fun: "Inbox", plain: "Inbox" },
  actionItems: { fun: "My tasks", plain: "My tasks" },
  people: { fun: "Team", plain: "Team" },
  agent: { fun: "Assistant", plain: "Assistant" },
  settings: { fun: "Settings", plain: "Settings" },
} as const;

export function label(key: keyof typeof LABELS, flavor: boolean): string {
  const l = LABELS[key];
  return flavor ? l.fun : l.plain;
}
