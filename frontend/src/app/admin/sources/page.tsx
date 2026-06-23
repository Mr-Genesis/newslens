"use client";

import { useEffect, useState, useCallback } from "react";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import {
  getAdminSources,
  createAdminSource,
  type AdminSource,
} from "@/lib/api";

export default function AdminSourcesPage() {
  const [sources, setSources] = useState<AdminSource[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [form, setForm] = useState({ name: "", url: "", rss_url: "", region: "in", category: "" });
  const [adding, setAdding] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setSources(await getAdminSources());
      setState("ready");
    } catch {
      setState("error");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function add() {
    if (!form.name.trim() || !form.url.trim()) {
      setMsg("Name and URL are required.");
      return;
    }
    setAdding(true);
    setMsg(null);
    try {
      await createAdminSource({
        name: form.name.trim(),
        url: form.url.trim(),
        rss_url: form.rss_url.trim() || undefined,
        region: form.region.trim() || undefined,
        category: form.category.trim() || undefined,
      });
      setForm({ name: "", url: "", rss_url: "", region: "in", category: "" });
      await load();
      setMsg("Source added.");
    } catch {
      setMsg("Couldn't add that source (duplicate URL?).");
    } finally {
      setAdding(false);
    }
  }

  return (
    <div className="mx-auto max-w-[640px] w-full px-[var(--space-lg)] py-[var(--space-lg)]">
      <h1 className="text-hero text-[var(--text-primary)] mb-1">Sources</h1>
      <p className="text-mono text-[var(--text-muted)] mb-[var(--space-lg)]">
        {sources.length} feeds &middot; admin
      </p>

      {/* Add form */}
      <div className="rounded-[var(--radius-lg)] bg-[var(--surface)] border border-[var(--border-subtle)] p-[var(--space-md)] mb-[var(--space-lg)] flex flex-col gap-2">
        <Input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <Input placeholder="Site URL" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} />
        <Input placeholder="RSS URL (optional)" value={form.rss_url} onChange={(e) => setForm({ ...form, rss_url: e.target.value })} />
        <div className="flex gap-2">
          <Input placeholder="Region (in/global)" value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} />
          <Input placeholder="Category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
        </div>
        <div className="flex items-center gap-3">
          <Button variant="primary" size="sm" onClick={add} loading={adding}>Add source</Button>
          {msg && <span className="text-mono text-[var(--text-muted)]">{msg}</span>}
        </div>
      </div>

      {state === "loading" && <p className="text-mono text-[var(--text-muted)]">Loading…</p>}
      {state === "error" && <p className="text-small text-[var(--text-muted)]">Couldn&apos;t load sources.</p>}
      {state === "ready" && (
        <div className="flex flex-col divide-y divide-[var(--border-subtle)]">
          {sources.map((s) => (
            <div key={s.id} className="py-3 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-small text-[var(--text-primary)] truncate">{s.name}</p>
                <p className="text-mono text-[var(--text-ghost)] truncate">
                  {(s.region || "—").toUpperCase()}
                  {s.category ? ` · ${s.category}` : ""}
                </p>
              </div>
              {s.is_paywalled && <Badge variant="paywall" size="sm">PAYWALL</Badge>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
