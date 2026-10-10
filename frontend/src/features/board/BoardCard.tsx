// A kanban card. Sortable wrapper + presentational body (reused by the drag overlay).
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { MessageSquare, GitBranch } from "lucide-react";
import type { Project, WorkItem } from "@/api/types";
import { Avatar, cn } from "@/components/ui";
import { BlockedTag, DueChip, LabelChips, PointsChip, PriorityGlyph, TypeIcon, isDone } from "@/features/items/common";

export function CardBody({ item, project, dragging, overlay }: { item: WorkItem; project: Project | undefined; dragging?: boolean; overlay?: boolean }) {
  const done = isDone(project, item.status);
  return (
    <div className={cn("panel p-2.5 pl-3 relative select-none transition-shadow", "hover:border-border-strong", dragging && "opacity-40", overlay && "glow-teal rotate-[1.5deg] cursor-grabbing", done && "opacity-75")}>
      {item.blocked && <span className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r bg-rust" aria-hidden />}
      <div className="flex items-center gap-1.5 text-[11px]">
        <TypeIcon project={project} type={item.type} />
        <span className="num text-text-3 font-semibold">{item.key}</span>
        <PriorityGlyph priority={item.priority} />
        <span className="flex-1" />
        {item.blocked && <BlockedTag reason={item.blocked_reason} />}
      </div>
      <div className={cn("text-[13px] leading-snug mt-1 font-medium", done && "line-through text-text-2")}>{item.title}</div>
      <div className="flex items-center gap-1.5 mt-2 flex-wrap">
        <LabelChips labels={item.labels} max={2} />
        <span className="flex-1" />
        <DueChip due={item.due_date} done={done} />
        {item.child_count > 0 && <span className="inline-flex items-center gap-0.5 text-[10px] text-text-3 num" title="Children"><GitBranch size={11} />{item.child_count}</span>}
        {item.comment_count > 0 && <span className="inline-flex items-center gap-0.5 text-[10px] text-text-3 num" title="Comments"><MessageSquare size={11} />{item.comment_count}</span>}
        <PointsChip points={item.points} />
        <Avatar user={item.assignee} size={20} />
      </div>
    </div>
  );
}

export function BoardCard({ item, project, onOpen }: { item: WorkItem; project: Project | undefined; onOpen: (id: string) => void }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: item.id, data: { type: "card" } });
  return (
    <div ref={setNodeRef} style={{ transform: CSS.Translate.toString(transform), transition }} {...attributes} {...listeners}
      role="button" tabIndex={0} aria-label={`${item.key} ${item.title}`} className="cursor-grab active:cursor-grabbing focus-visible:outline-none focus-visible:[&>div]:border-teal"
      onClick={() => onOpen(item.id)} onKeyDown={(e) => { if (e.key === "Enter") onOpen(item.id); }}>
      <CardBody item={item} project={project} dragging={isDragging} />
    </div>
  );
}
