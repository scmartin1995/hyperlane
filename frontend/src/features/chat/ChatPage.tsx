import { EmptyState, PageHeader } from "@/components/ui";

export default function ChatPage() {
  return (
    <div>
      <PageHeader eyebrow="Coming online" title="ChatPage" />
      <EmptyState icon="🛠️" title="Under construction" body="This page is being built." />
    </div>
  );
}
