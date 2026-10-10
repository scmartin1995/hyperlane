// Quick-add parser: "Call Sam about the brakes !high @fri #ops"  → title/priority/due/tags
import { addDays, format, nextDay, type Day } from "date-fns";
import type { Priority } from "@/api/types";

const DAYS: Record<string, Day> = { sun: 0, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6 };

export function parseDue(token: string, from = new Date()): string | null {
  const t = token.toLowerCase();
  if (t === "today") return format(from, "yyyy-MM-dd");
  if (t === "tomorrow" || t === "tmrw") return format(addDays(from, 1), "yyyy-MM-dd");
  if (t === "nextweek" || t === "next-week") return format(addDays(from, 7), "yyyy-MM-dd");
  const m = t.match(/^(\d+)d$/); if (m) return format(addDays(from, Number(m[1])), "yyyy-MM-dd");
  const d = DAYS[t.slice(0, 3)]; if (d !== undefined && t.length <= 9) return format(nextDay(from, d), "yyyy-MM-dd");
  if (/^\d{4}-\d{2}-\d{2}$/.test(t)) return t;
  return null;
}

export function parseQuickAdd(raw: string): { title: string; priority?: Priority; due_date?: string; tags: string[] } {
  const tags: string[] = []; let priority: Priority | undefined; let due: string | undefined;
  const words = raw.trim().split(/\s+/).filter((w) => {
    if (/^!(critical|high|med|medium|low)$/i.test(w)) { const p = w.slice(1).toLowerCase(); priority = (p === "med" ? "medium" : p) as Priority; return false; }
    if (w.startsWith("@") && w.length > 1) { const d = parseDue(w.slice(1)); if (d) { due = d; return false; } }
    if (w.startsWith("#") && w.length > 1) { tags.push(w.slice(1).toLowerCase()); return false; }
    return true;
  });
  return { title: words.join(" "), priority, due_date: due, tags };
}
