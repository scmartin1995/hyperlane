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
      theme: "dark",
      flavor: true,
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
    { name: "hyperlane-ui", partialize: (s) => ({ theme: s.theme, flavor: s.flavor, projectId: s.projectId, sidebarCollapsed: s.sidebarCollapsed, soundOn: s.soundOn }) },
  ),
);

/** Flavored vs plain labels. Plain labels are always shown as subtitles so nobody is lost. */
export const LABELS = {
  home: { fun: "Mission Control", plain: "Home" },
  board: { fun: "Pit Wall", plain: "Board" },
  backlog: { fun: "Hangar", plain: "Backlog" },
  sprints: { fun: "Laps", plain: "Sprints" },
  reports: { fun: "Telemetry", plain: "Reports" },
  intake: { fun: "Comms", plain: "Intake" },
  actionItems: { fun: "My Checklist", plain: "Action items" },
  people: { fun: "Pit Crew", plain: "People" },
  agent: { fun: "Navigator", plain: "Agent" },
  settings: { fun: "Garage", plain: "Settings" },
} as const;

export function label(key: keyof typeof LABELS, flavor: boolean): string {
  const l = LABELS[key];
  return flavor ? l.fun : l.plain;
}
