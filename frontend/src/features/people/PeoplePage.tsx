import { EmptyState, PageHeader } from "@/components/ui";

export default function PeoplePage() {
  return (
    <div>
      <PageHeader eyebrow="Coming online" title="PeoplePage" />
      <EmptyState icon="🛠️" title="Under construction" body="This page is being built." />
    </div>
  );
}
