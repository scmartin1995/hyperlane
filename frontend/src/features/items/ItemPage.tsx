import { EmptyState, PageHeader } from "@/components/ui";

export default function ItemPage() {
  return (
    <div>
      <PageHeader eyebrow="Coming online" title="ItemPage" />
      <EmptyState icon="🛠️" title="Under construction" body="This page is being built." />
    </div>
  );
}
