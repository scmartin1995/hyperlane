import { EmptyState, PageHeader } from "@/components/ui";

export default function SettingsPage() {
  return (
    <div>
      <PageHeader eyebrow="Coming online" title="SettingsPage" />
      <EmptyState icon="🛠️" title="Under construction" body="This page is being built." />
    </div>
  );
}
