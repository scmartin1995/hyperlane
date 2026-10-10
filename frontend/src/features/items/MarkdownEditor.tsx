// Markdown field with view/edit/preview modes. Ctrl+Enter saves, Esc cancels.
import { useEffect, useState } from "react";
import { Eye, Pencil } from "lucide-react";
import { Button, Markdown, Textarea, cn } from "@/components/ui";

export function MarkdownEditor({ label, value, placeholder, onSave, editing, onEditingChange, hint, className }: {
  label: string; value: string | null | undefined; placeholder: string; onSave: (v: string) => void;
  editing?: boolean; onEditingChange?: (e: boolean) => void; hint?: string; className?: string;
}) {
  const [internal, setInternal] = useState(false);
  const isEditing = editing ?? internal;
  const setEditing = (e: boolean) => { setInternal(e); onEditingChange?.(e); };
  const [draft, setDraft] = useState(value ?? "");
  const [preview, setPreview] = useState(false);
  useEffect(() => { if (isEditing) { setDraft(value ?? ""); setPreview(false); } }, [isEditing]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = () => { if ((value ?? "") !== draft) onSave(draft); setEditing(false); };
  return (
    <section className={cn("group", className)}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="eyebrow">{label}</span>
        {!isEditing && <Button size="xs" variant="ghost" icon={Pencil} onClick={() => setEditing(true)} className="opacity-0 group-hover:opacity-100 focus:opacity-100" aria-label={`Edit ${label}`}>Edit</Button>}
        {isEditing && <Button size="xs" variant="ghost" icon={preview ? Pencil : Eye} onClick={() => setPreview((p) => !p)}>{preview ? "Write" : "Preview"}</Button>}
      </div>
      {!isEditing ? (
        value ? <div onDoubleClick={() => setEditing(true)} className="rounded-[8px] px-0.5 cursor-text"><Markdown>{value}</Markdown></div>
          : <button type="button" onClick={() => setEditing(true)} className="w-full text-left text-sm text-text-3 italic border border-dashed border-border rounded-[8px] px-3 py-2 hover:border-border-strong hover:text-text-2">{placeholder}</button>
      ) : (
        <div className="space-y-2 animate-in">
          {preview ? <div className="min-h-[80px] rounded-[8px] border border-border px-3 py-2"><Markdown>{draft || "*Nothing yet*"}</Markdown></div>
            : <Textarea autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} placeholder={placeholder} className="min-h-[140px] font-mono text-[13px]"
                onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); save(); } else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setEditing(false); } }} />}
          <div className="flex items-center gap-2">
            <Button size="sm" variant="primary" onClick={save}>Save</Button>
            <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
            <span className="text-[11px] text-text-3 ml-auto">{hint ?? "Markdown · Ctrl+Enter to save · Esc to cancel"}</span>
          </div>
        </div>
      )}
    </section>
  );
}
