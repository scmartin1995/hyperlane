import { EmptyState, PageHeader } from "@/components/ui";

export default function IntakePage() {
  return (
    <div>
      <PageHeader eyebrow="Coming online" title="IntakePage" />
      <EmptyState icon="🛠️" title="Under construction" body="This page is being built." />
    </div>
  );
}
