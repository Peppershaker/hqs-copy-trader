"use client";

import { useState, useCallback, useEffect } from "react";
import { useAppStore } from "@/stores/app-store";
import { api } from "@/lib/api-client";
import type {
  ReconcileFollowerData,
  ReconcilePositionEntry,
  ReconcileApplyRequest,
} from "@/lib/types";

interface EntryDecision {
  action: "use_inferred" | "manual" | "use_default";
  manualMultiplier: string;
  blacklisted: boolean;
}

type DecisionMap = Record<string, EntryDecision>;

const SCENARIO_LABELS: Record<string, string> = {
  common_same_dir: "Same direction",
  common_diff_dir: "Opposite direction",
  master_only: "Master only",
};

const SCENARIO_COLORS: Record<string, string> = {
  common_same_dir: "bg-success/20 text-success",
  common_diff_dir: "bg-warning/20 text-warning",
  master_only: "bg-accent/20 text-accent",
};

function decisionKey(followerId: string, symbol: string) {
  return `${followerId}:${symbol}`;
}

function buildDefaults(followers: ReconcileFollowerData[]): DecisionMap {
  const map: DecisionMap = {};
  for (const follower of followers) {
    for (const entry of follower.entries) {
      const key = decisionKey(follower.follower_id, entry.symbol);
      if (entry.scenario === "common_same_dir" && entry.inferred_multiplier != null) {
        map[key] = {
          action: "use_inferred",
          manualMultiplier: String(entry.inferred_multiplier),
          blacklisted: entry.is_blacklisted,
        };
      } else {
        map[key] = {
          action: "use_default",
          manualMultiplier: "",
          blacklisted: true,
        };
      }
    }
  }
  return map;
}

function EntryRow({
  followerId,
  entry,
  decision,
  onChange,
}: {
  followerId: string;
  entry: ReconcilePositionEntry;
  decision: EntryDecision;
  onChange: (d: EntryDecision) => void;
}) {
  const hasInferred = entry.inferred_multiplier != null;

  return (
    <tr className="border-b border-border/30 hover:bg-card/50">
      {/* Symbol */}
      <td className="px-3 py-2 font-medium">{entry.symbol}</td>

      {/* Scenario badge */}
      <td className="px-3 py-2">
        <span
          className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${SCENARIO_COLORS[entry.scenario] ?? ""}`}
        >
          {SCENARIO_LABELS[entry.scenario] ?? entry.scenario}
        </span>
      </td>

      {/* Positions */}
      <td className="px-3 py-2 text-xs text-muted-foreground">
        {entry.master_side} {entry.master_qty}
      </td>
      <td className="px-3 py-2 text-xs text-muted-foreground">
        {entry.follower_side
          ? `${entry.follower_side} ${entry.follower_qty}`
          : "—"}
      </td>

      {/* Multiplier action radio group */}
      <td className="px-3 py-2">
        <div className="flex flex-col gap-1">
          <label className="flex items-center gap-1.5 text-xs cursor-pointer">
            <input
              type="radio"
              name={`action-${followerId}-${entry.symbol}`}
              checked={decision.action === "use_inferred"}
              disabled={!hasInferred}
              onChange={() => onChange({ ...decision, action: "use_inferred" })}
              className="h-3 w-3 accent-primary"
            />
            <span className={!hasInferred ? "text-muted-foreground/40" : ""}>
              Inferred ({hasInferred ? `${entry.inferred_multiplier}x` : "n/a"})
            </span>
          </label>
          <label className="flex items-center gap-1.5 text-xs cursor-pointer">
            <input
              type="radio"
              name={`action-${followerId}-${entry.symbol}`}
              checked={decision.action === "manual"}
              onChange={() => onChange({ ...decision, action: "manual" })}
              className="h-3 w-3 accent-primary"
            />
            <span>Manual</span>
            {decision.action === "manual" && (
              <input
                type="number"
                step="0.01"
                min="0"
                value={decision.manualMultiplier}
                onChange={(e) =>
                  onChange({ ...decision, manualMultiplier: e.target.value })
                }
                className="ml-1 w-16 rounded border border-border bg-background px-1.5 py-0.5 text-xs"
                placeholder="1.0"
                autoFocus
              />
            )}
          </label>
          <label className="flex items-center gap-1.5 text-xs cursor-pointer">
            <input
              type="radio"
              name={`action-${followerId}-${entry.symbol}`}
              checked={decision.action === "use_default"}
              onChange={() => onChange({ ...decision, action: "use_default" })}
              className="h-3 w-3 accent-primary"
            />
            <span>Default ({entry.current_multiplier}x)</span>
          </label>
        </div>
      </td>

      {/* Blacklist checkbox */}
      <td className="px-3 py-2 text-center">
        <input
          type="checkbox"
          checked={decision.blacklisted}
          onChange={(e) =>
            onChange({ ...decision, blacklisted: e.target.checked })
          }
          className="h-4 w-4 rounded border-border accent-primary"
        />
      </td>
    </tr>
  );
}

function FollowerSection({
  follower,
  decisions,
  onDecisionChange,
}: {
  follower: ReconcileFollowerData;
  decisions: DecisionMap;
  onDecisionChange: (key: string, d: EntryDecision) => void;
}) {
  return (
    <div className="mb-4">
      <div className="mb-2 flex items-center gap-2">
        <h3 className="font-semibold">{follower.follower_name}</h3>
        <span className="text-xs text-muted-foreground">
          Base multiplier: {follower.base_multiplier}x
        </span>
      </div>
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-card/50 text-left text-xs text-muted-foreground">
              <th className="px-3 py-2 font-medium">Symbol</th>
              <th className="px-3 py-2 font-medium">Scenario</th>
              <th className="px-3 py-2 font-medium">Master</th>
              <th className="px-3 py-2 font-medium">Follower</th>
              <th className="px-3 py-2 font-medium">Multiplier</th>
              <th className="px-3 py-2 font-medium text-center">Blacklist</th>
            </tr>
          </thead>
          <tbody>
            {follower.entries.map((entry) => {
              const key = decisionKey(follower.follower_id, entry.symbol);
              return (
                <EntryRow
                  key={key}
                  followerId={follower.follower_id}
                  entry={entry}
                  decision={decisions[key]!}
                  onChange={(d) => onDecisionChange(key, d)}
                />
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function ReconcileDialog() {
  const reconcileData = useAppStore((s) => s.reconcileData);
  const reconcileOpen = useAppStore((s) => s.reconcileOpen);
  const setReconcileOpen = useAppStore((s) => s.setReconcileOpen);
  const setReconcileData = useAppStore((s) => s.setReconcileData);
  const addAlert = useAppStore((s) => s.addAlert);

  const [decisions, setDecisions] = useState<DecisionMap>({});
  const [submitting, setSubmitting] = useState(false);

  // Initialize decisions when reconcile data changes
  useEffect(() => {
    if (reconcileData?.followers) {
      setDecisions(buildDefaults(reconcileData.followers));
    }
  }, [reconcileData]);

  const handleDecisionChange = useCallback((key: string, d: EntryDecision) => {
    setDecisions((prev) => ({ ...prev, [key]: d }));
  }, []);

  const close = useCallback(() => {
    setReconcileOpen(false);
    setReconcileData(null);
  }, [setReconcileOpen, setReconcileData]);

  const handleApply = async () => {
    if (!reconcileData) return;
    setSubmitting(true);
    try {
      const request: ReconcileApplyRequest = {
        followers: reconcileData.followers.map((follower) => ({
          follower_id: follower.follower_id,
          decisions: follower.entries.map((entry) => {
            const key = decisionKey(follower.follower_id, entry.symbol);
            const d = decisions[key]!;
            let multiplier: number | null = null;
            if (d.action === "use_inferred") {
              multiplier = entry.inferred_multiplier;
            } else if (d.action === "manual") {
              multiplier = parseFloat(d.manualMultiplier) || null;
            }
            return {
              symbol: entry.symbol,
              action: d.action,
              multiplier,
              blacklist: d.blacklisted,
            };
          }),
        })),
      };
      await api.applyReconciliation(request);
      addAlert({
        type: "info",
        message: "Reconciliation applied — replication started",
      });
      close();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to apply reconciliation";
      addAlert({ type: "error", message: msg });
    } finally {
      setSubmitting(false);
    }
  };

  if (!reconcileOpen || !reconcileData) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-3xl max-h-[85vh] flex flex-col rounded-xl border border-border bg-background shadow-2xl">
        {/* Header */}
        <div className="shrink-0 border-b border-border px-6 py-4">
          <h2 className="text-lg font-bold">Position Reconciliation</h2>
          <p className="text-sm text-muted-foreground">
            Review master vs follower positions before starting replication.
            Choose a multiplier action and optionally blacklist symbols.
          </p>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {reconcileData.followers.map((follower) => (
            <FollowerSection
              key={follower.follower_id}
              follower={follower}
              decisions={decisions}
              onDecisionChange={handleDecisionChange}
            />
          ))}
        </div>

        {/* Footer */}
        <div className="shrink-0 flex items-center gap-2 border-t border-border px-6 py-4">
          <button
            onClick={handleApply}
            disabled={submitting}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/80 disabled:opacity-50"
          >
            {submitting ? "Applying..." : "Apply & Start Replication"}
          </button>
          <button
            onClick={close}
            disabled={submitting}
            className="ml-auto rounded-md border border-border px-4 py-2 text-sm hover:bg-card disabled:opacity-50"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
