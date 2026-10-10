import { EmptyState, PageHeader } from "@/components/ui";

export default function BacklogPage() {
  return (
    <div>
      <PageHeader eyebrow="Coming online" title="BacklogPage" />
      <EmptyState icon="🛠️" title="Under construction" body="This page is being built." />
    </div>
  );
}
