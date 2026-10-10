// Wizard state, persisted so a refresh or a crash mid-setup doesn't lose progress.
export interface WizardState { step: number; wsName: string; theme: "dark" | "light"; flavor: boolean; projectId: string | null; seeded: string | null }
export interface StepProps { state: WizardState; update: (p: Partial<WizardState>) => void; next: () => void; back: () => void }
export const STEPS = [
  { key: "workspace", title: "Name your workspace", plain: "Name and theme" },
  { key: "profile", title: "Create your profile", plain: "Who you are on the team" },
  { key: "template", title: "Choose a project type", plain: "Workflow and item types" },
  { key: "seed", title: "Seed the backlog", plain: "Assistant, import or demo" },
  { key: "connect", title: "Connect & finish", plain: "Claude, Slack, email" },
] as const;
const KEY = "hyperlane-welcome";
export const DEFAULT_STATE: WizardState = { step: 0, wsName: "", theme: "dark", flavor: true, projectId: null, seeded: null };
export function loadState(): WizardState { try { const raw = localStorage.getItem(KEY); return raw ? { ...DEFAULT_STATE, ...(JSON.parse(raw) as Partial<WizardState>) } : DEFAULT_STATE; } catch { return DEFAULT_STATE; } }
export function saveState(s: WizardState) { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { /* ignore */ } }
export function clearState() { try { localStorage.removeItem(KEY); } catch { /* ignore */ } }
export const EMOJIS = ["💻", "🧭", "🛠️", "🎯", "📊", "🧪", "🎨", "📝", "💡", "🌱", "🚀", "⚡", "🔍", "📚", "🤝", "🧠", "🌟", "☕", "🎧", "🦊", "🐙", "🌊", "🌿", "🧩"];
// Brand accent swatches (from tokens.css) — the only hard-coded colors in the wizard.
export const SWATCHES = ["#e4b963", "#27cfc3", "#bc553c", "#9b6bc0", "#67a671", "#e07a5f", "#306376", "#f9dfad", "#869791", "#f7f2f0"];
