import { EmptyState, PageHeader } from "@/components/ui";

export default function SprintsPage() {
  return (
    <div>
      <PageHeader eyebrow="Coming online" title="SprintsPage" />
      <EmptyState icon="🛠️" title="Under construction" body="This page is being built." />
    </div>
  );
}
