import { EmptyState, PageHeader } from "@/components/ui";

export default function BoardPage() {
  return (
    <div>
      <PageHeader eyebrow="Coming online" title="BoardPage" />
      <EmptyState icon="🛠️" title="Under construction" body="This page is being built." />
    </div>
  );
}
