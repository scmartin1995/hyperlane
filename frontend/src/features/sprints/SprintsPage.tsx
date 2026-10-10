// Sprints. List at /sprints, detail at /sprints/:id/:tab.
import { useParams } from "react-router-dom";
import { SprintList } from "./SprintList";
import { SprintDetail } from "./SprintDetail";
import { NoProject, useProjectId } from "./common";

export default function SprintsPage() {
  const { id, tab } = useParams<{ id?: string; tab?: string }>();
  const pid = useProjectId();
  if (!pid) return <NoProject what="sprints" />;
  if (id) return <SprintDetail sprintId={id} tab={(tab as "overview" | "plan" | "retro") ?? "overview"} projectId={pid} />;
  return <SprintList projectId={pid} />;
}
