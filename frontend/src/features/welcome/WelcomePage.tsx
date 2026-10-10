import { EmptyState, PageHeader } from "@/components/ui";

export default function WelcomePage() {
  return (
    <div>
      <PageHeader eyebrow="Coming online" title="WelcomePage" />
      <EmptyState icon="🛠️" title="Under construction" body="This page is being built." />
    </div>
  );
}
