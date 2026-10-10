// Full-page work item: /items/:id
import { useNavigate, useParams, Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { useProject } from "@/api/queries";
import { useUI, label } from "@/lib/store";
import { Kbd } from "@/components/ui";
import { useItem } from "./hooks";
import { ItemDetail } from "./ItemDetail";

export default function ItemPage() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const ui = useUI();
  const { data: item } = useItem(id);
  const { data: project } = useProject(item?.project_id);
  return (
    <div className="max-w-[1000px] mx-auto">
      <nav className="flex items-center gap-1.5 text-xs text-text-3 mb-4 flex-wrap" aria-label="Breadcrumb">
        <Link to="/backlog" className="hover:text-text no-underline text-text-3">{label("backlog", ui.flavor)}</Link>
        {project && <><ChevronRight size={12} /><span>{project.icon} {project.name}</span></>}
        {item?.parent && <><ChevronRight size={12} /><Link to={`/items/${item.parent.id}`} className="hover:text-text no-underline text-text-3 num">{item.parent.key}</Link></>}
        {item && <><ChevronRight size={12} /><span className="num text-text-2">{item.key}</span></>}
        <span className="flex-1" />
        <span className="hidden md:inline-flex items-center gap-1">Edit description <Kbd>e</Kbd></span>
      </nav>
      {id && <ItemDetail id={id} onArchived={() => nav("/backlog")} />}
    </div>
  );
}
