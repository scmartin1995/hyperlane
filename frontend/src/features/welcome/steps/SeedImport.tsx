// "Import from Excel/CSV": upload → preview with per-column mapping → commit.
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload, Check } from "lucide-react";
import { api } from "@/api/client";
import type { ImportCommitResult, ImportPreview, WorkItem } from "@/api/types";
import { Button, Select, Toggle, toast } from "@/components/ui";

const FIELDS = ["title", "type", "description", "acceptance_criteria", "status", "priority", "points", "assignee", "parent", "epic", "feature", "labels", "due_date"] as const;

export function SeedImport({ projectId, onDone }: { projectId: string; onDone: (created: WorkItem[]) => void }) {
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [createUsers, setCreateUsers] = useState(true);
  const up = useMutation({
    mutationFn: (f: File) => { const fd = new FormData(); fd.append("file", f); return api.upload<ImportPreview>(`/projects/${projectId}/import/excel/preview`, fd); },
    onSuccess: (p) => { setPreview(p); setMapping(p.mapping ?? {}); },
    onError: (e) => toast.error("Couldn't read that file", String(e)),
  });
  const sheet = useMutation({
    mutationFn: (s: string) => { const fd = new FormData(); fd.append("file", file!); fd.append("sheet", s); return api.upload<ImportPreview>(`/projects/${projectId}/import/excel/preview`, fd); },
    onSuccess: (p) => { setPreview(p); setMapping(p.mapping ?? {}); },
  });
  const commit = useMutation({
    mutationFn: () => api.post<ImportCommitResult>(`/projects/${projectId}/import/excel/commit`, { file_token: preview!.file_token, sheet: preview!.sheet, mapping, create_missing_users: createUsers }),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["items"] }); qc.invalidateQueries({ queryKey: ["users"] }); toast.fun(`Imported ${r.created.length} items.`, r.skipped ? `${r.skipped} rows skipped.` : undefined); r.warnings.forEach((w) => toast.info("Import note", w)); onDone(r.created); },
    onError: (e) => toast.error("Import failed", String(e)),
  });
  const hasTitle = Object.values(mapping).includes("title");
  return (
    <div className="space-y-3 animate-in">
      {!preview ? (
        <label className="panel panel-cut p-6 flex flex-col items-center gap-2 cursor-pointer hover:border-teal border-dashed">
          <Upload size={22} className="text-teal" />
          <span className="font-display font-semibold">{file ? file.name : "Choose an .xlsx / .csv"}</span>
          <span className="text-xs text-text-3">One row per item. A header row helps. Columns like title, type, status, points, assignee, epic/parent are auto-detected.</span>
          <input type="file" accept=".xlsx,.xls,.csv" className="sr-only" onChange={(e) => { const f = e.target.files?.[0] ?? null; setFile(f); if (f) up.mutate(f); }} />
          {up.isPending && <span className="text-xs text-teal">Reading…</span>}
        </label>
      ) : (
        <>
          <div className="flex items-center gap-3 text-xs text-text-3 flex-wrap">
            <span><b className="text-text num">{preview.total_rows}</b> rows · <b className="text-text num">{preview.columns.length}</b> columns</span>
            {preview.sheets.length > 1 && <label className="inline-flex items-center gap-1">Sheet <Select value={preview.sheet} onChange={(e) => sheet.mutate(e.target.value)} className="h-7 text-xs !w-auto">{preview.sheets.map((s) => <option key={s}>{s}</option>)}</Select></label>}
            <Toggle checked={createUsers} onChange={setCreateUsers} label={<span className="text-xs">Create missing people</span>} />
            <Button size="xs" variant="ghost" onClick={() => { setPreview(null); setFile(null); }}>Different file</Button>
          </div>
          {preview.notes.length > 0 && <ul className="text-xs text-text-3 list-disc pl-4">{preview.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
          <div className="overflow-x-auto rounded-[8px] border border-border max-h-[320px]">
            <table className="text-xs min-w-full">
              <thead className="bg-surface-2 sticky top-0">
                <tr>{preview.columns.map((c) => <th key={c} className="px-2 py-1.5 text-left font-display whitespace-nowrap align-top">
                  <div className="text-text-2 truncate max-w-[160px]" title={c}>{c}</div>
                  <Select value={mapping[c] ?? ""} onChange={(e) => setMapping((m) => ({ ...m, [c]: e.target.value || null }))} className="h-7 text-[11px] mt-1 !w-auto min-w-[120px]" aria-label={`Map column ${c}`}><option value="">— skip —</option>{FIELDS.map((f) => <option key={f} value={f}>{f}</option>)}</Select>
                </th>)}</tr>
              </thead>
              <tbody>{preview.rows.slice(0, 8).map((r, i) => <tr key={i} className="border-t border-border">{preview.columns.map((c) => <td key={c} className="px-2 py-1 whitespace-nowrap max-w-[200px] truncate text-text-2">{String(r[c] ?? "")}</td>)}</tr>)}</tbody>
            </table>
          </div>
          {!hasTitle && <p className="text-xs text-rust-light">Map one column to <b>title</b> to continue.</p>}
          <div className="flex justify-end"><Button variant="primary" icon={Check} loading={commit.isPending} disabled={!hasTitle} onClick={() => commit.mutate()}>Import {preview.total_rows} rows</Button></div>
        </>
      )}
    </div>
  );
}
