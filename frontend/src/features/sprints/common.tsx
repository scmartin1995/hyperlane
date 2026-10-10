// Small shared bits for the frontend-b features (sprints, reports, people, action items, intake, chat, settings).
import { Component, Suspense, lazy, type ComponentType, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Button, Drawer, EmptyState, Skeleton, Spinner, cn } from "@/components/ui";
import { useUI } from "@/lib/store";

export const useProjectId = () => useUI((s) => s.projectId);

export function NoProject({ what = "this page" }: { what?: string }) {
  return (
    <EmptyState icon="🏁" title="No project on the grid yet" body={`Pick or create a project to use ${what}.`}
      action={<Link to="/welcome"><Button variant="primary">Open the welcome setup</Button></Link>} />
  );
}

export function LoadingRows({ n = 4, className }: { n?: number; className?: string }) {
  return <div className={cn("space-y-2", className)}>{Array.from({ length: n }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>;
}

export function Help({ text }: { text: string }) {
  return <span className="inline-flex items-center justify-center w-4 h-4 rounded-full border border-border-strong text-[10px] text-text-3 cursor-help select-none" title={text} aria-label={text}>?</span>;
}

/* Error boundary so an optional lazy import (e.g. the other agent's ItemDetail) can't take a page down. */
export class Boundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}

type ItemDetailProps = { itemId: string; onClose?: () => void };
// Resolved at build time: if the other frontend half hasn't written ItemDetail.tsx yet, the glob is empty and we fall back to a link.
// The real component (features/items/ItemDetail.tsx) takes { id, compact?, onOpenItem?, onArchived? }; we pass both prop shapes.
type AnyDetail = ComponentType<Record<string, unknown>>;
const detailModules = import.meta.glob("/src/features/items/ItemDetail.tsx") as Record<string, () => Promise<{ ItemDetail?: AnyDetail; default?: AnyDetail }>>;
const loader = Object.values(detailModules)[0];
const FallbackDetail = ({ itemId }: ItemDetailProps) => (
  <div className="p-6"><EmptyState icon="🔗" title="Item detail is on its way" body="Open the full item page instead." action={<Link to={`/items/${itemId}`}><Button variant="teal">Open item</Button></Link>} /></div>
);
const LazyItemDetail: ComponentType<ItemDetailProps> = loader
  ? lazy(() => loader().then((m) => {
      const Real = m.ItemDetail ?? m.default;
      if (!Real) return { default: FallbackDetail };
      return { default: (p: ItemDetailProps) => <Real id={p.itemId} itemId={p.itemId} compact onArchived={p.onClose} onClose={p.onClose} /> };
    }))
  : FallbackDetail;

/** Drawer that shows a work item. Safe even if the ItemDetail component doesn't exist. */
export function ItemDrawer({ itemId, onClose, title }: { itemId: string | null; onClose: () => void; title?: string }) {
  return (
    <Drawer open={!!itemId} onClose={onClose} title={title ?? "Work item"} eyebrow="Detail" width={640}>
      {itemId && (
        <Boundary fallback={<FallbackDetail itemId={itemId} />}>
          <Suspense fallback={<div className="p-8 flex justify-center"><Spinner /></div>}><LazyItemDetail itemId={itemId} onClose={onClose} /></Suspense>
        </Boundary>
      )}
    </Drawer>
  );
}
