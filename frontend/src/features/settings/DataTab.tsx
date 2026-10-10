import { useEffect, useState } from "react";
import { Database, Download, ShieldCheck } from "lucide-react";
import { useHealth } from "@/api/queries";
import { Button } from "@/components/ui";

export function DataTab() {
  const { data: h } = useHealth();
  const [exportOk, setExportOk] = useState(false);
  useEffect(() => { fetch("/api/export", { method: "HEAD", credentials: "same-origin" }).then((r) => setExportOk(r.ok)).catch(() => setExportOk(false)); }, []);
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <section className="panel panel-cut p-4">
        <div className="hairline mb-3" />
        <div className="eyebrow">Storage</div><h2 className="text-base inline-flex items-center gap-2"><Database size={16} /> One SQLite file</h2>
        <p className="text-sm text-text-2 mt-2">Everything lives in <code>./data/hyperlane.db</code> inside the Hyperlane folder (override with <code>HYPERLANE_DB_PATH</code>). Back it up by copying the file; WAL mode means it's safe to copy while running.</p>
        <ul className="text-xs text-text-3 mt-3 space-y-1"><li>Uploads for Excel import: <code>./data/uploads/</code></li><li>Version: <span className="num">{h?.version ?? "–"}</span> · profiles <span className="num">{h?.profiles ?? "–"}</span> · projects <span className="num">{h?.projects ?? "–"}</span></li></ul>
        {exportOk && <a href="/api/export" download className="inline-block mt-3 no-underline"><Button variant="outline" icon={Download}>Export JSON</Button></a>}
      </section>
      <section className="panel p-4">
        <div className="eyebrow">Privacy</div><h2 className="text-base inline-flex items-center gap-2"><ShieldCheck size={16} className="text-green" /> Local-first, by design</h2>
        <ul className="text-sm text-text-2 mt-2 space-y-1.5 list-disc pl-5">
          <li>No analytics, no telemetry, no CDNs at runtime. Fonts are bundled.</li>
          <li>Prompts go only to the LLM provider you configured in <code>.env</code>; nothing else leaves the machine unless you route it to Slack, Teams or email.</li>
          <li>Private action items and notes are returned only to the profile that owns them. Add a PIN on your profile to lock them.</li>
          <li>Secrets stay in <code>.env</code>, never in the database.</li>
        </ul>
      </section>
    </div>
  );
}
