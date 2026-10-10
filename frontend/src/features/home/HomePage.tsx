// Mission Control: greeting, health strip, active sprint, your lane, action items, intake, activity, quick actions.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Sparkles, Flag } from "lucide-react";
import { useMe, useMeOverview, useMetricsOverview, useProject, useProjectSummary } from "@/api/queries";
import { useUI } from "@/lib/store";
import { Button, EmptyState, Kbd } from "@/components/ui";
import { useHotkey, useSprints } from "@/features/items/hooks";
import { CreateItemModal } from "@/features/items/CreateItemModal";
import { HealthStrip } from "./HealthStrip";
import { ActionItemsCard, ActiveSprintCard, ActivityFeed, Greeting, IntakeCard, YourLane } from "./HomeCards";

export default function HomePage() {
  const ui = useUI();
  const nav = useNavigate();
  const pid = ui.projectId ?? undefined;
  const { data: me } = useMe();
  const { data: project } = useProject(pid);
  const summary = useProjectSummary(pid);
  const metrics = useMetricsOverview(pid);
  const overview = useMeOverview();
  const { data: sprints } = useSprints(pid);
  const [createOpen, setCreateOpen] = useState(false);
  useHotkey("c", () => setCreateOpen(true), { enabled: !createOpen });
  const activeSprint = sprints?.find((s) => s.state === "active") ?? summary.data?.active_sprint ?? undefined;

  if (!pid) return (
    <div className="space-y-6">
      <Greeting name={me?.name} emoji={me?.emoji} flavor={ui.flavor} />
      <EmptyState icon="🏁" title="No project on the grid" body="Create a project to unlock the board, backlog and telemetry. Takes a minute." action={<Button variant="primary" onClick={() => nav("/welcome")}>Run setup</Button>} />
    </div>
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <Greeting name={me?.name} emoji={me?.emoji} flavor={ui.flavor} />
        <div className="flex items-center gap-2 flex-wrap">
          <Button variant="primary" icon={Plus} onClick={() => setCreateOpen(true)}>New item <Kbd>c</Kbd></Button>
          <Button variant="outline" icon={Sparkles} onClick={() => ui.setAgentOpen(true, { project_id: pid })}>Open agent <Kbd>/</Kbd></Button>
          <Button variant="secondary" icon={Flag} onClick={() => nav(activeSprint ? `/sprints/${activeSprint.id}` : "/sprints")}>{activeSprint ? "Sprint" : "Plan sprint"}</Button>
        </div>
      </div>

      <HealthStrip metrics={metrics.data} summary={summary.data} loading={metrics.isLoading || (metrics.isError && summary.isLoading)} estimation={project?.settings.estimation} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <ActiveSprintCard sprint={activeSprint} project={project} />
          <YourLane overview={overview.data} loading={overview.isLoading} project={project} meId={me?.id} />
        </div>
        <div className="space-y-4">
          <ActionItemsCard overview={overview.data} />
          <IntakeCard />
          <ActivityFeed pid={pid} />
        </div>
      </div>
      <CreateItemModal open={createOpen} onClose={() => setCreateOpen(false)} projectId={pid} onCreated={(it) => nav(`/items/${it.id}`)} />
    </div>
  );
}
