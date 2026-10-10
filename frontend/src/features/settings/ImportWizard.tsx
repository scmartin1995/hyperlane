// Excel/CSV import: upload → preview + mapping → commit → results. Reusable: <ImportWizard pid=... onDone=... />
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Check, FileSpreadsheet, Upload } from "lucide-react";
import type { ImportPreview, WorkItem } from "@/api/types";
import { Badge, Button, EmptyState, Field, Select, Toggle, celebrate, toast, cn } from "@/components/ui";
import { useImportCommit, useImportPreview } from "./hooks";

const FIELDS: { key: string; label: string; hint?: string }[] = [
  { key: "title", label: "Title", hint: "required" }, { key: "type", label: "Type" }, { key: "description", label: "Description" }, { key: "status", label: "Status" }, { key: "priority", label: "Priority" },
  { key: "points", label: "Points" }, { key: "assignee", label: "Assignee" }, { key: "parent", label: "Parent (key or title)" }, { key: "epic", label: "Epic name" }, { key: "feature", label: "Feature name" }, { key: "labels", label: "Labels" }, { key: "due_date", label: "Due date" },
];
type Result = { created: WorkItem[]; skipped: number; warnings: string[] };

export function ImportWizard({ pid, onDone }: { pid: string; onDone?: (r: Result) => void }) {
  const preview = useImportPreview(pid); const commit = useImportCommit(pid);
  const [file, setFile] = useState<File | null>(null);
  const [pv, setPv] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [createUsers, setCreateUsers] = useState(true);
  const [result, setResult] = useState<Result | null>(null);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const step = result ? 4 : pv ? 2 : 1;

  const upload = (f: File, sheet?: string) => {
    setFile(f); const form = new FormData(); form.append("file", f); if (sheet) form.append("sheet", sheet);
    preview.mutate(form, { onSuccess: (p) => { setPv(p); setMapping(p.mapping ?? {}); }, onError: (e) => toast.error("Couldn't read the file", (e as Error).message) });
  };
  const go = () => {
    if (!pv) return; if (!mapping.title) return toast.error("Map a Title column first");
    commit.mutate({ file_token: pv.file_token, sheet: pv.sheet, mapping, create_missing_users: createUsers }, { onSuccess: (r) => { setResult(r); celebrate("small"); toast.fun(`${r.created.length} items imported`); onDone?.(r); }, onError: (e) => toast.error("Import failed", (e as Error).message) });
  };
  const reset = () => { setFile(null); setPv(null); setMapping({}); setResult(null); };
  const used = new Set(Object.values(mapping).filter(Boolean));

  return (
    <div className="space-y-4">
      <ol className="flex items-center gap-2 text-xs">{["Upload", "Map columns", "Import", "Done"].map((s, i) => <li key={s} className={cn("inline-flex items-center gap-1.5", step >= i + 1 ? "text-gold" : "text-text-3")}><span className={cn("w-5 h-5 rounded-full border inline-flex items-center justify-center font-display font-bold text-[10px]", step >= i + 1 ? "border-gold" : "border-border-strong")}>{step > i + 1 ? <Check size={10} /> : i + 1}</span>{s}{i < 3 && <span className="w-6 h-px bg-border ml-1" />}</li>)}</ol>

      {step === 1 && (
        <div onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) upload(f); }}
          className={cn("panel panel-cut p-10 text-center border-dashed transition-colors", drag && "border-teal glow-teal")}>
          <FileSpreadsheet size={36} className="mx-auto text-text-3 mb-3" />
          <h2 className="text-base">Drop an Excel or CSV file</h2>
          <p className="text-sm text-text-3 mt-1 mb-4">One row per item. Columns like Title, Type, Status, Points, Assignee, Epic/Parent are detected automatically; you'll confirm the mapping next.</p>
          <input ref={inputRef} type="file" accept=".xlsx,.xls,.csv" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); }} />
          <Button variant="primary" icon={Upload} loading={preview.isPending} onClick={() => inputRef.current?.click()}>Choose file</Button>
        </div>
      )}

      {step === 2 && pv && (
        <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
          <section className="panel p-4 space-y-3 self-start">
            <div><div className="eyebrow">File</div><div className="text-sm truncate">{file?.name}</div><div className="text-xs text-text-3">{pv.total_rows} rows · {pv.columns.length} columns</div></div>
            {pv.sheets.length > 1 && <Field label="Sheet"><Select value={pv.sheet} onChange={(e) => file && upload(file, e.target.value)}>{pv.sheets.map((s) => <option key={s} value={s}>{s}</option>)}</Select></Field>}
            <div className="eyebrow">Column mapping</div>
            {FIELDS.map((f) => (
              <label key={f.key} className="grid grid-cols-[110px_1fr] items-center gap-2 text-xs"><span className={cn(f.hint && "font-semibold")}>{f.label}{f.hint && <span className="text-rust"> *</span>}</span>
                <Select className="h-7 text-xs" value={mapping[f.key] ?? ""} onChange={(e) => setMapping((m) => ({ ...m, [f.key]: e.target.value || null }))}><option value="">— skip —</option>{pv.columns.map((c) => <option key={c} value={c} disabled={used.has(c) && mapping[f.key] !== c}>{c}</option>)}</Select></label>
            ))}
            <Toggle checked={createUsers} onChange={setCreateUsers} label="Create missing people from the Assignee column" />
            {pv.notes.length > 0 && <ul className="text-[11px] text-text-3 list-disc pl-4">{pv.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
            <div className="flex gap-2 pt-2"><Button variant="ghost" onClick={reset}>Start over</Button><Button variant="primary" className="flex-1" loading={commit.isPending} onClick={go}>Import {pv.total_rows} rows</Button></div>
          </section>
          <section className="panel overflow-auto max-h-[70vh]">
            <table className="text-xs w-full"><thead><tr className="bg-surface-2/60 sticky top-0">{pv.columns.map((c) => { const mapped = Object.entries(mapping).find(([, v]) => v === c)?.[0]; return <th key={c} className="text-left px-2 py-2 whitespace-nowrap border-b border-border"><div className="eyebrow">{c}</div>{mapped && <Badge size="xs" color="var(--teal)">{mapped}</Badge>}</th>; })}</tr></thead>
              <tbody>{pv.rows.map((r, i) => <tr key={i} className="border-b border-border">{pv.columns.map((c) => <td key={c} className="px-2 py-1 max-w-[220px] truncate" title={String(r[c] ?? "")}>{String(r[c] ?? "")}</td>)}</tr>)}</tbody></table>
            {pv.total_rows > pv.rows.length && <p className="text-[11px] text-text-3 p-2">Showing the first {pv.rows.length} of {pv.total_rows} rows.</p>}
          </section>
        </div>
      )}

      {step === 4 && result && (
        <div className="panel panel-cut p-6">
          <div className="hairline mb-4" />
          <EmptyState icon="✅" title={`${result.created.length} items imported`} body={`${result.skipped} skipped.${result.warnings.length ? ` ${result.warnings.length} warnings below.` : ""}`}
            action={<div className="flex gap-2"><Button variant="ghost" onClick={reset}>Import another</Button><Link to="/backlog"><Button variant="primary">Open the backlog</Button></Link></div>} />
          {result.warnings.length > 0 && <ul className="mt-4 text-xs text-text-2 list-disc pl-5 space-y-0.5">{result.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}
        </div>
      )}
    </div>
  );
}
