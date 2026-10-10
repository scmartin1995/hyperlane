// Activity feed + status transition timeline for one item.
import { ArrowRight, CalendarRange, MessageSquare, Pencil, PlusCircle, Trash2, Move, Sparkles, type LucideIcon } from "lucide-react";
import type { Activity, Project, StatusTransition } from "@/api/types";
import { ago, fmtDateTime, stateOf, categoryColor } from "@/lib/format";
import { Skeleton, cn } from "@/components/ui";
import { useItemActivity, useItemTransitions } from "./hooks";

export function actionIcon(action: string): { icon: LucideIcon; color: string } {
  const a = action.toLowerCase();
  if (a.includes("create")) return { icon: PlusCircle, color: "var(--green)" };
  if (a.includes("comment")) return { icon: MessageSquare, color: "var(--teal)" };
  if (a.includes("move") || a.includes("status")) return { icon: Move, color: "var(--gold)" };
  if (a.includes("delete") || a.includes("archive")) return { icon: Trash2, color: "var(--rust)" };
  if (a.includes("sprint")) return { icon: CalendarRange, color: "var(--purple-light)" };
  if (a.includes("agent")) return { icon: Sparkles, color: "var(--gold)" };
  return { icon: Pencil, color: "var(--text-3)" };
}

export function ActivityList({ rows, loading, emptyText = "Nothing has happened yet." }: { rows: Activity[] | undefined; loading?: boolean; emptyText?: string }) {
  if (loading) return <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-8" />)}</div>;
  if (!rows?.length) return <div className="text-sm text-text-3 py-3">{emptyText}</div>;
  return (
    <ul className="flex flex-col gap-4">
      {rows.map((a) => { const { icon: Icon, color } = actionIcon(a.action); return (
        <li key={a.id} className="flex items-start gap-3 text-sm">
          <span className="inline-flex w-8 h-8 items-center justify-center rounded-full shrink-0" style={{ color, background: `color-mix(in oklab, ${color} 14%, var(--surface))` }}><Icon size={14} /></span>
          <div className="flex-1 min-w-0 flex flex-col gap-0.5">
            <div className="line-clamp-2 leading-snug"><span className="font-semibold">{a.actor_name ?? "System"}</span> <span className="text-text-2">{tidySummary(a.summary, a.actor_name)}</span></div>
            <div className="text-xs text-text-3" title={fmtDateTime(a.at)}>{ago(a.at)}</div>
          </div>
        </li>
      ); })}
    </ul>
  );
}
/** "Kai Tanaka commented on AP-3" → "commented on AP-3"; "Created story…" → "created story…"; status keys read as words. */
function tidySummary(summary: string, actor: string | null): string {
  let t = summary;
  if (actor && t.startsWith(actor)) t = t.slice(actor.length).trim();
  else if (/^[A-Z][a-z]/.test(t)) t = t.charAt(0).toLowerCase() + t.slice(1);
  return t.replace(/\b([a-z]+)_([a-z]+)\b/g, "$1 $2");
}
const fmt = (v: unknown) => (v == null || v === "" ? "∅" : typeof v === "object" ? JSON.stringify(v) : String(v));

export function ItemActivityTab({ itemId }: { itemId: string }) {
  const q = useItemActivity(itemId);
  return <ActivityList rows={q.data} loading={q.isLoading} />;
}

export function TransitionsTimeline({ itemId, project }: { itemId: string; project: Project | undefined }) {
  const q = useItemTransitions(itemId);
  if (q.isLoading) return <div className="space-y-2">{[0, 1].map((i) => <Skeleton key={i} className="h-8" />)}</div>;
  const rows = q.data ?? [];
  if (!rows.length) return <div className="text-sm text-text-3 py-3">No status changes yet. Drag it across the board to start the clock.</div>;
  return (
    <ol className="relative pl-5 border-l border-border ml-2 space-y-3">
      {rows.map((t, i) => {
        const next = rows[i + 1];
        const dur = next ? durationLabel(t.at, next.at) : durationLabel(t.at, new Date().toISOString()) + " so far";
        return (
          <li key={t.id} className="relative text-sm">
            <span className="absolute -left-[25px] top-1 w-3 h-3 rounded-full border-2 border-bg" style={{ background: categoryColor(t.to_category as never) }} />
            <div className="flex items-center gap-2 flex-wrap">
              {t.from_status && <><StateName project={project} k={t.from_status} /><ArrowRight size={12} className="text-text-3" /></>}
              <StateName project={project} k={t.to_status} strong />
              <span className="text-[11px] text-text-3" title={fmtDateTime(t.at)}>{ago(t.at)}</span>
            </div>
            <div className="text-[11px] text-text-3 mt-0.5 num">{dur}</div>
          </li>
        );
      })}
    </ol>
  );
}
function StateName({ project, k, strong }: { project: Project | undefined; k: string; strong?: boolean }) {
  const s = stateOf(project, k);
  return <span className={cn("font-display", strong ? "font-semibold" : "text-text-2")} style={{ color: strong ? s?.color || undefined : undefined }}>{s?.name ?? k}</span>;
}
function durationLabel(a: string, b: string) {
  const ms = Math.max(0, new Date(b).getTime() - new Date(a).getTime());
  const h = ms / 36e5;
  if (h < 1) return `${Math.round(ms / 6e4)}m`;
  if (h < 48) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)}d`;
}
