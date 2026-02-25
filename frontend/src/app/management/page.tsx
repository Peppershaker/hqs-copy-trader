"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api-client";
import { useAppStore } from "@/stores/app-store";
import type { Follower, SymbolMultiplier, AuditLogEntry } from "@/lib/types";
import { formatCurrency, formatNumber, formatPnL } from "@/lib/utils";

// ============================================================
// Follower Management Card
// ============================================================
function FollowerPanel({ follower }: { follower: Follower }) {
  const systemStatus = useAppStore((s) => s.systemStatus);
  const followerPositions = useAppStore((s) => s.followerPositions);
  const [multipliers, setMultipliers] = useState<SymbolMultiplier[]>([]);
  const [expanded, setExpanded] = useState(false);

  const connected = systemStatus?.followers?.[follower.id]?.connected ?? false;
  const positions = followerPositions[follower.id] || [];
  const totalPnl = positions.reduce((sum, p) => sum + p.total_pnl, 0);

  useEffect(() => {
    if (expanded) {
      api
        .getMultipliers(follower.id)
        .then(setMultipliers)
        .catch(() => {});
    }
  }, [expanded, follower.id]);

  const handleRemoveOverride = async (symbol: string) => {
    try {
      await api.removeMultiplier(follower.id, symbol);
      setMultipliers((prev) => prev.filter((m) => m.symbol !== symbol));
    } catch {
      alert("Failed to remove override");
    }
  };

  return (
    <div className="rounded-lg border border-border bg-card">
      {/* Header bar */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between p-4 text-left hover:bg-card/80"
      >
        <div className="flex items-center gap-3">
          <span
            className={`h-2.5 w-2.5 rounded-full ${
              connected
                ? "bg-success"
                : follower.enabled
                  ? "bg-warning"
                  : "bg-muted-foreground"
            }`}
          />
          <div>
            <span className="font-medium">{follower.name}</span>
            <span className="ml-2 text-xs text-muted-foreground">
              {follower.base_multiplier}× · {follower.account_id}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-xs text-muted-foreground">P&L</div>
            <div
              className={`text-sm font-medium ${totalPnl >= 0 ? "text-success" : "text-destructive"}`}
            >
              {formatPnL(totalPnl)}
            </div>
          </div>
          <div className="text-right">
            <div className="text-xs text-muted-foreground">Positions</div>
            <div className="text-sm font-medium">{positions.length}</div>
          </div>
          <span className="text-muted-foreground">{expanded ? "▲" : "▼"}</span>
        </div>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-border p-4 space-y-4">
          {/* Connection info */}
          <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
            <div>
              <span className="text-xs text-muted-foreground">Host</span>
              <p>
                {follower.host}:{follower.port}
              </p>
            </div>
            <div>
              <span className="text-xs text-muted-foreground">Locate Δ</span>
              <p>${follower.max_locate_price_delta}</p>
            </div>
            <div>
              <span className="text-xs text-muted-foreground">
                Locate Retry
              </span>
              <p>{follower.locate_retry_timeout}s</p>
            </div>
            <div>
              <span className="text-xs text-muted-foreground">Auto-accept</span>
              <p>{follower.auto_accept_locates ? "Yes" : "No"}</p>
            </div>
          </div>

          {/* Active positions */}
          {positions.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wider">
                Open Positions
              </h4>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-xs text-muted-foreground">
                      <th className="py-1 text-left">Symbol</th>
                      <th className="py-1 text-left">Side</th>
                      <th className="py-1 text-right">Qty</th>
                      <th className="py-1 text-right">Avg Cost</th>
                      <th className="py-1 text-right">P&L</th>
                      <th className="py-1 text-right">Multiplier</th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((pos) => (
                      <tr
                        key={pos.symbol}
                        className="border-b border-border/50"
                      >
                        <td className="py-1.5 font-medium">{pos.symbol}</td>
                        <td className="py-1.5">
                          <span
                            className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                              pos.side === "Long"
                                ? "bg-success/20 text-success"
                                : "bg-destructive/20 text-destructive"
                            }`}
                          >
                            {pos.side}
                          </span>
                        </td>
                        <td className="py-1.5 text-right">
                          {formatNumber(pos.quantity)}
                        </td>
                        <td className="py-1.5 text-right">
                          {formatCurrency(pos.avg_cost)}
                        </td>
                        <td
                          className={`py-1.5 text-right font-medium ${
                            pos.total_pnl >= 0
                              ? "text-success"
                              : "text-destructive"
                          }`}
                        >
                          {formatPnL(pos.total_pnl)}
                        </td>
                        <td className="py-1.5 text-right text-muted-foreground">
                          {pos.effective_multiplier ?? "—"}×
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Symbol multiplier overrides */}
          {multipliers.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wider">
                Symbol Multiplier Overrides
              </h4>
              <div className="flex flex-wrap gap-2">
                {multipliers.map((m) => (
                  <span
                    key={m.symbol}
                    className="inline-flex items-center gap-1 rounded-md border border-border bg-card/50 px-2 py-1 text-xs"
                  >
                    <span className="font-medium">{m.symbol}</span>
                    <span className="text-muted-foreground">
                      {m.multiplier}×
                    </span>
                    <span className="text-muted-foreground/60">
                      ({m.source})
                    </span>
                    {m.source === "user_override" && (
                      <button
                        onClick={() => handleRemoveOverride(m.symbol)}
                        className="ml-1 text-destructive hover:text-destructive/80"
                        title="Remove override"
                      >
                        ×
                      </button>
                    )}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ============================================================
// Audit Log Panel
// ============================================================
function AuditLogPanel() {
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.getAuditLog({ limit: 50 });
      setEntries(res.entries);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, [load]);

  const levelColor = (level: string) => {
    switch (level) {
      case "ERROR":
        return "text-destructive";
      case "WARNING":
        return "text-warning";
      case "INFO":
        return "text-primary";
      default:
        return "text-muted-foreground";
    }
  };

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-base font-semibold">Audit Log</h2>
        <button
          onClick={load}
          disabled={loading}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          {loading ? "Loading..." : "Refresh"}
        </button>
      </div>
      <div className="max-h-80 overflow-y-auto space-y-1">
        {entries.length === 0 && (
          <p className="text-sm text-muted-foreground py-4 text-center">
            No audit log entries yet.
          </p>
        )}
        {entries.map((entry) => (
          <div
            key={entry.id}
            className="flex gap-2 text-xs py-1 border-b border-border/30"
          >
            <span className="text-muted-foreground/60 whitespace-nowrap">
              {new Date(entry.timestamp).toLocaleTimeString()}
            </span>
            <span className={`font-medium w-14 ${levelColor(entry.level)}`}>
              {entry.level}
            </span>
            <span className="text-muted-foreground w-20 truncate">
              {entry.category}
            </span>
            {entry.follower_id && (
              <span className="text-accent w-16 truncate">
                {entry.follower_id}
              </span>
            )}
            {entry.symbol && (
              <span className="font-medium w-12">{entry.symbol}</span>
            )}
            <span className="flex-1 truncate">{entry.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================
// Management Page
// ============================================================
export default function ManagementPage() {
  const followers = useAppStore((s) => s.followers);
  const setFollowers = useAppStore((s) => s.setFollowers);
  const setMasterConfig = useAppStore((s) => s.setMasterConfig);

  const loadData = useCallback(async () => {
    try {
      const [master, followers] = await Promise.all([
        api.getMaster(),
        api.getFollowers(),
      ]);
      setMasterConfig(master);
      setFollowers(followers);
    } catch {
      // silent
    }
  }, [setMasterConfig, setFollowers]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Management</h1>
        <p className="text-sm text-muted-foreground">
          Monitor follower accounts and view audit log
        </p>
      </div>

      {/* Follower panels */}
      <div className="space-y-3">
        {followers.map((f) => (
          <FollowerPanel key={f.id} follower={f} />
        ))}
        {followers.length === 0 && (
          <p className="text-sm text-muted-foreground py-8 text-center">
            No follower accounts configured. Go to Settings to add followers.
          </p>
        )}
      </div>

      {/* Audit log */}
      <AuditLogPanel />
    </div>
  );
}
