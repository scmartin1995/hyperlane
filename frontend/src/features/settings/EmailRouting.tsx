// Where do new requests go? A default project, with [KEY] in the subject as an override.
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useProjects, useWorkspace, qk } from "@/api/queries";
import type { Workspace } from "@/api/types";
import { Field, Select, toast } from "@/components/ui";

export function EmailRouting() {
  const { data: ws } = useWorkspace();
  const { data: projects } = useProjects();
  const qc = useQueryClient();
  const save = useMutation({ mutationFn: (intake_project_id: string) => api.patch<Workspace>("/workspace", { settings: { intake_project_id } }), onSuccess: () => { qc.invalidateQueries({ queryKey: qk.workspace }); toast.success("Routing saved"); } });
  const current = (ws?.settings?.intake_project_id as string | undefined) ?? "";
  return (
    <section className="panel p-4 grid gap-3 md:grid-cols-[1fr_1fr] items-start">
      <div>
        <div className="eyebrow">Request routing</div>
        <h3 className="font-display font-bold">Where new requests land</h3>
        <p className="text-xs text-text-3 mt-1">Every incoming email (or form request) becomes an item at the top of that project's backlog, labelled <code>needs-triage</code>. Put a project key in the subject, like <code>[GR]</code>, to route a single request elsewhere. The full email thread is in <Link to="/intake">the request log</Link>.</p>
      </div>
      <Field label="Default project" hint="Falls back to the first active project when unset.">
        <Select value={current} onChange={(e) => save.mutate(e.target.value)}>
          <option value="">First active project</option>
          {projects?.map((p) => <option key={p.id} value={p.id}>{p.icon} {p.name} · {p.key}</option>)}
        </Select>
      </Field>
    </section>
  );
}
