// Garage · Settings. Tabs: workspace / project / agent / integrations / import / data.
import { useNavigate, useParams } from "react-router-dom";
import { useUI, label } from "@/lib/store";
import { PageHeader, Tabs } from "@/components/ui";
import { WorkspaceTab } from "./WorkspaceTab";
import { ProjectTab } from "./ProjectTab";
import { AgentTab } from "./AgentTab";
import { IntegrationsTab } from "./IntegrationsTab";
import { ImportWizard } from "./ImportWizard";
import { DataTab } from "./DataTab";
import { NoProject, useProjectId } from "@/features/sprints/common";

const TABS = [{ key: "workspace", label: "Workspace" }, { key: "project", label: "Project" }, { key: "agent", label: "Agent" }, { key: "integrations", label: "Integrations" }, { key: "import", label: "Import" }, { key: "data", label: "Data" }] as const;
type Tab = (typeof TABS)[number]["key"];

export default function SettingsPage() {
  const { tab = "workspace" } = useParams<{ tab?: Tab }>();
  const nav = useNavigate();
  const flavor = useUI((s) => s.flavor);
  const pid = useProjectId();
  const t = (TABS.some((x) => x.key === tab) ? tab : "workspace") as Tab;
  return (
    <div>
      <PageHeader eyebrow="Settings" title={label("settings", flavor)} subtitle="Workspace, project workflow, the agent, integrations and your data." />
      <Tabs className="mb-4 flex-wrap" value={t} onChange={(x) => nav(`/settings/${x}`)} tabs={TABS.map((x) => ({ key: x.key, label: x.label }))} />
      {t === "workspace" && <WorkspaceTab />}
      {t === "project" && (pid ? <ProjectTab pid={pid} /> : <NoProject what="project settings" />)}
      {t === "agent" && <AgentTab />}
      {t === "integrations" && <IntegrationsTab />}
      {t === "import" && (pid ? <ImportWizard pid={pid} /> : <NoProject what="import" />)}
      {t === "data" && <DataTab />}
    </div>
  );
}
