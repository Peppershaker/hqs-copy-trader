"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { api } from "@/lib/api-client";
import { useAppStore } from "@/stores/app-store";
import type { LogEntry, LogDirectory } from "@/lib/types";

// ============================================================
// Database Reset Panel
// ============================================================
function DatabaseResetPanel() {
  const [confirming, setConfirming] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [result, setResult] = useState<{
    ok: boolean;
    message: string;
  } | null>(null);

  const handleReset = async () => {
    setResetting(true);
    setResult(null);
    try {
      const res = await api.resetDatabase();
      setResult({ ok: true, message: res.message });
    } catch (e) {
      setResult({
        ok: false,
        message: e instanceof Error ? e.message : "Reset failed",
      });
    } finally {
      setResetting(false);
      setConfirming(false);
    }
  };

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <h2 className="text-base font-semibold mb-1">Database</h2>
      <p className="text-xs text-muted-foreground mb-3">
        Drop all tables and recreate them. This destroys all configuration,
        followers, audit logs, and order history.
      </p>

      {!confirming ? (
        <button
          onClick={() => setConfirming(true)}
          className="rounded-md border border-destructive/50 px-3 py-1.5 text-sm text-destructive hover:bg-destructive/10"
        >
          Reinitialize Database
        </button>
      ) : (
        <div className="flex items-center gap-3">
          <span className="text-sm text-destructive font-medium">
            Are you sure? All data will be lost.
          </span>
          <button
            onClick={handleReset}
            disabled={resetting}
            className="rounded-md bg-destructive px-3 py-1.5 text-sm font-medium text-white hover:bg-destructive/80 disabled:opacity-50"
          >
            {resetting ? "Resetting..." : "Yes, reset everything"}
          </button>
          <button
            onClick={() => setConfirming(false)}
            className="rounded-md border border-border px-3 py-1.5 text-sm hover:bg-card/80"
          >
            Cancel
          </button>
        </div>
      )}

      {result && (
        <p
          className={`mt-2 text-sm ${result.ok ? "text-success" : "text-destructive"}`}
        >
          {result.message}
        </p>
      )}
    </div>
  );
}

// ============================================================
// Log Level Badge
// ============================================================
function LevelBadge({ level }: { level: string }) {
  const color = (() => {
    switch (level) {
      case "ERROR":
      case "CRITICAL":
        return "text-destructive";
      case "WARNING":
        return "text-warning";
      case "DEBUG":
        return "text-muted-foreground/60";
      default:
        return "text-primary";
    }
  })();
  return <span className={`w-16 font-medium ${color}`}>{level}</span>;
}

// ============================================================
// Log Viewer Panel
// ============================================================
const DEFAULT_OMIT_PATTERNS = ["QuoteUpdated", "Heartbeat", "ClientResponse"];

function LogViewerPanel() {
  const wsLogEntries = useAppStore((s) => s.logEntries);
  const clearWsLogs = useAppStore((s) => s.clearLogEntries);

  // Which source tab is active
  const [activeSource, setActiveSource] = useState<"app" | "das_bridge">(
    "app",
  );

  // Message omit filters (patterns whose lines are hidden)
  const [omitPatterns, setOmitPatterns] = useState<string[]>(DEFAULT_OMIT_PATTERNS);
  const [showFilterConfig, setShowFilterConfig] = useState(false);
  const [newPattern, setNewPattern] = useState("");

  // Initial load from REST (backfill entries from before WS connected)
  const [backfill, setBackfill] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const loadBackfill = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.getDevLogs({ limit: 500 });
      setBackfill(res.entries);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBackfill();
  }, [loadBackfill]);

  // Merge backfill + WS entries, deduplicate by seq, sort ascending
  const allEntries = (() => {
    const map = new Map<number, LogEntry>();
    for (const e of backfill) map.set(e.seq, e);
    for (const e of wsLogEntries) map.set(e.seq, e);
    return Array.from(map.values()).sort((a, b) => a.seq - b.seq);
  })();

  const filteredEntries = allEntries.filter(
    (e) =>
      e.source === activeSource &&
      !omitPatterns.some((pat) => pat && e.message.includes(pat)),
  );

  // Auto-scroll
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [filteredEntries.length, autoScroll]);

  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    // Re-enable auto-scroll if user scrolls near bottom
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 40);
  };

  const handleClear = async () => {
    clearWsLogs();
    setBackfill([]);
    try {
      await api.clearDevLogs();
    } catch {
      // ignore
    }
  };

  const appCount = allEntries.filter((e) => e.source === "app").length;
  const bridgeCount = allEntries.filter(
    (e) => e.source === "das_bridge",
  ).length;

  return (
    <div className="rounded-lg border border-border bg-card flex flex-col" style={{ height: "calc(100vh - 280px)", minHeight: "400px" }}>
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <div className="flex items-center gap-1">
          <button
            onClick={() => setActiveSource("app")}
            className={`rounded-md px-3 py-1 text-sm font-medium transition-colors ${
              activeSource === "app"
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:text-foreground hover:bg-muted"
            }`}
          >
            App Logs
            {appCount > 0 && (
              <span className="ml-1.5 text-xs opacity-60">{appCount}</span>
            )}
          </button>
          <button
            onClick={() => setActiveSource("das_bridge")}
            className={`rounded-md px-3 py-1 text-sm font-medium transition-colors ${
              activeSource === "das_bridge"
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:text-foreground hover:bg-muted"
            }`}
          >
            DAS Bridge
            {bridgeCount > 0 && (
              <span className="ml-1.5 text-xs opacity-60">{bridgeCount}</span>
            )}
          </button>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadBackfill}
            disabled={loading}
            className="text-xs text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            {loading ? "Loading..." : "Refresh"}
          </button>
          <button
            onClick={handleClear}
            className="text-xs text-muted-foreground hover:text-destructive"
          >
            Clear
          </button>
          <button
            onClick={() => setShowFilterConfig((v) => !v)}
            className={`text-xs ${showFilterConfig ? "text-primary" : "text-muted-foreground hover:text-foreground"}`}
          >
            Filter{omitPatterns.length > 0 && ` (${omitPatterns.length})`}
          </button>
          <label className="flex items-center gap-1 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="rounded"
            />
            Auto-scroll
          </label>
        </div>
      </div>

      {/* Filter config */}
      {showFilterConfig && (
        <div className="border-b border-border px-4 py-2 space-y-1.5 bg-muted/20">
          <div className="flex flex-wrap gap-1.5">
            {omitPatterns.map((pat) => (
              <span
                key={pat}
                className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-xs font-mono"
              >
                {pat}
                <button
                  onClick={() => setOmitPatterns((prev) => prev.filter((p) => p !== pat))}
                  className="text-muted-foreground hover:text-destructive ml-0.5"
                >
                  ×
                </button>
              </span>
            ))}
            {omitPatterns.length === 0 && (
              <span className="text-xs text-muted-foreground">No filters active</span>
            )}
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const v = newPattern.trim();
              if (v && !omitPatterns.includes(v)) {
                setOmitPatterns((prev) => [...prev, v]);
              }
              setNewPattern("");
            }}
            className="flex items-center gap-2"
          >
            <input
              value={newPattern}
              onChange={(e) => setNewPattern(e.target.value)}
              placeholder="Add pattern to omit…"
              className="rounded-md border border-border bg-background px-2 py-1 text-xs font-mono w-48 focus:outline-none focus:ring-1 focus:ring-primary"
            />
            <button
              type="submit"
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Add
            </button>
          </form>
        </div>
      )}

      {/* Log entries */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto font-mono text-xs p-2 space-y-px"
      >
        {filteredEntries.length === 0 && (
          <p className="text-muted-foreground text-center py-8">
            No {activeSource === "app" ? "app" : "DAS Bridge"} log entries yet.
          </p>
        )}
        {filteredEntries.map((entry) => (
          <div
            key={entry.seq}
            className="flex gap-2 py-0.5 hover:bg-muted/30 px-1 rounded"
          >
            <span className="text-muted-foreground/50 whitespace-nowrap shrink-0">
              {new Date(entry.timestamp * 1000).toLocaleTimeString([], {
                hour12: false,
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              })}
            </span>
            <LevelBadge level={entry.level} />
            <span className="text-muted-foreground/60 w-32 truncate shrink-0" title={entry.logger}>
              {entry.logger}
            </span>
            <span className="flex-1 whitespace-pre-wrap break-all">
              {entry.message}
            </span>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="border-t border-border px-4 py-1.5 text-xs text-muted-foreground flex items-center justify-between">
        <span>
          {filteredEntries.length} entries
          {!autoScroll && " (scroll paused)"}
        </span>
        <span>
          Streaming via WebSocket
        </span>
      </div>
    </div>
  );
}

// ============================================================
// Log Directory Panel
// ============================================================
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function LogDirectoryPanel() {
  const [dirs, setDirs] = useState<LogDirectory[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await api.getLogDirs();
      setDirs(res.directories);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const allSelected = dirs.length > 0 && selected.size === dirs.length;

  const toggleAll = () => {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(dirs.map((d) => d.name)));
    }
  };

  const toggle = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const handleDelete = async () => {
    if (selected.size === 0) return;
    setDeleting(true);
    try {
      await api.deleteLogDirs(Array.from(selected));
      setSelected(new Set());
      await load();
    } catch {
      // ignore
    } finally {
      setDeleting(false);
    }
  };

  const totalSize = dirs.reduce((sum, d) => sum + d.size_bytes, 0);
  const selectedSize = dirs
    .filter((d) => selected.has(d.name))
    .reduce((sum, d) => sum + d.size_bytes, 0);

  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-semibold">Log Files</h2>
          <span className="text-xs text-muted-foreground">
            {dirs.length} run{dirs.length !== 1 && "s"} &middot;{" "}
            {formatBytes(totalSize)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            disabled={loading}
            className="text-xs text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            Refresh
          </button>
          {selected.size > 0 && (
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="text-xs text-destructive hover:text-destructive/80 disabled:opacity-50"
            >
              {deleting
                ? "Deleting..."
                : `Delete ${selected.size} (${formatBytes(selectedSize)})`}
            </button>
          )}
        </div>
      </div>

      <div className="max-h-64 overflow-y-auto">
        {loading ? (
          <p className="text-xs text-muted-foreground text-center py-6">
            Loading...
          </p>
        ) : dirs.length === 0 ? (
          <p className="text-xs text-muted-foreground text-center py-6">
            No log directories found.
          </p>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border text-muted-foreground">
                <th className="px-4 py-1.5 text-left w-8">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={toggleAll}
                    className="rounded"
                  />
                </th>
                <th className="px-2 py-1.5 text-left">Run</th>
                <th className="px-2 py-1.5 text-left">Files</th>
                <th className="px-4 py-1.5 text-right">Size</th>
              </tr>
            </thead>
            <tbody>
              {dirs.map((d) => (
                <tr
                  key={d.name}
                  onClick={() => toggle(d.name)}
                  className="border-b border-border/50 hover:bg-muted/30 cursor-pointer"
                >
                  <td className="px-4 py-1.5">
                    <input
                      type="checkbox"
                      checked={selected.has(d.name)}
                      onChange={() => toggle(d.name)}
                      className="rounded"
                    />
                  </td>
                  <td className="px-2 py-1.5 font-mono">{d.name}</td>
                  <td className="px-2 py-1.5 text-muted-foreground">
                    {d.files.join(", ")}
                  </td>
                  <td className="px-4 py-1.5 text-right text-muted-foreground">
                    {formatBytes(d.size_bytes)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ============================================================
// Dev Page
// ============================================================
export default function DevPage() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">Developer Tools</h1>
        <p className="text-sm text-muted-foreground">
          Database management and live log viewer
        </p>
      </div>

      <DatabaseResetPanel />
      <LogDirectoryPanel />
      <LogViewerPanel />
    </div>
  );
}
