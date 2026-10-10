import { EmptyState, PageHeader } from "@/components/ui";

export default function HomePage() {
  return (
    <div>
      <PageHeader eyebrow="Coming online" title="HomePage" />
      <EmptyState icon="🛠️" title="Under construction" body="This page is being built." />
    </div>
  );
}
