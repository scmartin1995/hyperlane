// Insights · Reports. Tabs: overview / flow / velocity / forecast / evm.
import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useUI, label } from "@/lib/store";
import { PageHeader, Tabs, Kbd } from "@/components/ui";
import { NoProject, useProjectId } from "@/features/sprints/common";
import { OverviewTab } from "./OverviewTab";
import { FlowTab } from "./FlowTab";
import { VelocityTab } from "./VelocityTab";
import { ForecastTab } from "./ForecastTab";
import { EvmTab } from "./EvmTab";

const TABS = [{ key: "overview", label: "Overview" }, { key: "flow", label: "Flow" }, { key: "velocity", label: "Velocity" }, { key: "forecast", label: "Forecast" }, { key: "evm", label: "Earned value" }] as const;
type Tab = (typeof TABS)[number]["key"];

export default function ReportsPage() {
  const { tab = "overview" } = useParams<{ tab?: Tab }>();
  const nav = useNavigate();
  const flavor = useUI((s) => s.flavor);
  const pid = useProjectId();
  useEffect(() => {
    const k = (e: KeyboardEvent) => { const tag = (e.target as HTMLElement)?.tagName; if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return; const i = Number(e.key); if (i >= 1 && i <= TABS.length) nav(`/reports/${TABS[i - 1].key}`); };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, [nav]);
  if (!pid) return <NoProject what="reports" />;
  const t = (TABS.some((x) => x.key === tab) ? tab : "overview") as Tab;
  return (
    <div>
      <PageHeader eyebrow="Reports" title={label("reports", flavor)} subtitle="Flow, velocity, forecasts and earned value, explained in plain language."
        actions={<span className="hidden md:inline-flex items-center gap-1 text-xs text-text-3"><Kbd>1</Kbd>–<Kbd>5</Kbd> switch tab</span>} />
      <Tabs className="mb-4" value={t} onChange={(x) => nav(`/reports/${x}`)} tabs={TABS.map((x) => ({ key: x.key, label: x.label }))} />
      {t === "overview" && <OverviewTab pid={pid} />}
      {t === "flow" && <FlowTab pid={pid} />}
      {t === "velocity" && <VelocityTab pid={pid} />}
      {t === "forecast" && <ForecastTab pid={pid} />}
      {t === "evm" && <EvmTab pid={pid} />}
    </div>
  );
}
