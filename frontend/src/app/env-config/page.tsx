"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api-client";

// Parse .env text client-side to give live feedback.
// Returns { key, value } pairs, skipping comments and blanks.
function parseEnvText(text: string): { key: string; value: string }[] {
  const results: { key: string; value: string }[] = [];
  for (const rawLine of text.split("\n")) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const eqIdx = line.indexOf("=");
    if (eqIdx === -1) continue;
    const key = line.slice(0, eqIdx).trim();
    if (!key) continue;
    let value = line.slice(eqIdx + 1).trim();
    // Strip surrounding quotes
    if (
      (value.startsWith("'") && value.endsWith("'")) ||
      (value.startsWith('"') && value.endsWith('"'))
    ) {
      value = value.slice(1, -1);
    }
    results.push({ key, value });
  }
  return results;
}

export default function EnvConfigPage() {
  const [content, setContent] = useState("");
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [appliedKeys, setAppliedKeys] = useState<string[]>([]);

  const load = useCallback(async () => {
    try {
      const res = await api.getEnvConfig();
      setContent(res.content);
      setAppliedKeys(res.parsed_keys);
      setSavedAt(res.updated_at);
    } catch {
      // Not yet saved — leave blank
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      const res = await api.saveEnvConfig(content);
      setAppliedKeys(res.parsed_keys);
      setSavedAt(res.updated_at);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const preview = parseEnvText(content);
  const hasDasServers = preview.some((p) => p.key === "DAS_SERVERS");

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-xl font-bold">Environment Configuration</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Paste your full{" "}
          <span className="font-mono text-xs">.env</span> file content below.
          The configuration is persisted in the database and reloaded
          automatically on every startup.
        </p>
      </div>

      {/* Textarea */}
      <div className="space-y-2">
        <label className="text-xs font-medium text-muted-foreground">
          .env content
        </label>
        <textarea
          className="w-full h-96 rounded-md border border-border bg-card px-3 py-2 font-mono text-xs outline-none focus:ring-1 focus:ring-primary resize-y"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder={"# Paste your .env file here\nDAS_SERVERS='[...]'\nDAS_CONNECTION_TIMEOUT=30.0\n..."}
          spellCheck={false}
        />
      </div>

      {/* Live parse preview */}
      {preview.length > 0 && (
        <div className="rounded-lg border border-border bg-card p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">
              Detected variables ({preview.length})
            </span>
            {!hasDasServers && (
              <span className="text-xs text-warning">
                ⚠ DAS_SERVERS not found
              </span>
            )}
          </div>
          <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
            {preview.map(({ key, value }) => {
              const isDasServers = key === "DAS_SERVERS";
              const displayValue =
                value.length > 60 ? value.slice(0, 57) + "…" : value;
              return (
                <div
                  key={key}
                  className="flex items-baseline gap-2 rounded bg-muted/50 px-2 py-1"
                >
                  <span
                    className={`font-mono text-xs font-medium shrink-0 ${isDasServers ? "text-primary" : "text-foreground"}`}
                  >
                    {key}
                  </span>
                  <span className="font-mono text-xs text-muted-foreground truncate">
                    {isDasServers ? "(JSON array)" : displayValue || "(empty)"}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Last applied keys (from server) */}
      {appliedKeys.length > 0 && (
        <div className="text-xs text-muted-foreground">
          Last saved{savedAt ? ` · ${new Date(savedAt).toLocaleString()}` : ""}{" "}
          · {appliedKeys.length} variables applied to process
        </div>
      )}

      {error && <p className="text-sm text-destructive">{error}</p>}
      {success && (
        <p className="text-sm text-success">
          Saved and applied — backend is now using the new configuration.
        </p>
      )}

      <button
        onClick={handleSave}
        disabled={saving || preview.length === 0}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/80 disabled:opacity-50"
      >
        {saving ? "Saving…" : "Save & Apply"}
      </button>
    </div>
  );
}
