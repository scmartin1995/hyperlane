import { EmptyState, PageHeader } from "@/components/ui";

export default function ActionItemsPage() {
  return (
    <div>
      <PageHeader eyebrow="Coming online" title="ActionItemsPage" />
      <EmptyState icon="🛠️" title="Under construction" body="This page is being built." />
    </div>
  );
}
