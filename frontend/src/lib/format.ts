import { format, formatDistanceToNowStrict, isPast, parseISO } from "date-fns";
import type { Priority, Project, StatusCategory, WorkflowState } from "@/api/types";

export const fmtDate = (d: string | null | undefined, f = "MMM d") => (d ? format(parseISO(d), f) : "");
export const fmtDateTime = (d: string | null | undefined) => (d ? format(parseISO(d), "MMM d, HH:mm") : "");
export const ago = (d: string | null | undefined) => (d ? formatDistanceToNowStrict(parseISO(d), { addSuffix: true }) : "");
export const overdue = (d: string | null | undefined) => !!d && isPast(parseISO(d));

export const PRIORITY_ORDER: Priority[] = ["critical", "high", "medium", "low", "none"];
export const priorityColor = (p: Priority) => `var(--prio-${p})`;
export const priorityIcon: Record<Priority, string> = { critical: "🔥", high: "▲", medium: "■", low: "▼", none: "–" };

export const categoryColor = (c: StatusCategory) => `var(--cat-${c})`;

export function stateOf(project: Project | undefined, key: string): WorkflowState | undefined {
  return project?.workflow.find((s) => s.key === key);
}
export function typeOf(project: Project | undefined, key: string) {
  return project?.item_types.find((t) => t.key === key);
}
export const initials = (name: string) => name.split(/\s+/).map((s) => s[0]).join("").slice(0, 2).toUpperCase();

export const pct = (n: number, d: number) => (d > 0 ? Math.round((n / d) * 100) : 0);
export const n1 = (n: number | null | undefined) => (n == null ? "–" : Number.isInteger(n) ? String(n) : n.toFixed(1));
export const money = (n: number, currency = "USD") => new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 }).format(n);
