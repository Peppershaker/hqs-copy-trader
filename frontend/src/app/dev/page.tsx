"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { api } from "@/lib/api-client";
import { useAppStore } from "@/stores/app-store";
import type { LogEntry } from "@/lib/types";

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
function LogViewerPanel() {
  const wsLogEntries = useAppStore((s) => s.logEntries);
  const clearWsLogs = useAppStore((s) => s.clearLogEntries);

  // Which source tab is active
  const [activeSource, setActiveSource] = useState<"app" | "das_bridge">(
    "app",
  );

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
    (e) => e.source === activeSource,
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
      <LogViewerPanel />
    </div>
  );
}
