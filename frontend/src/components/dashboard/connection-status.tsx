"use client";

import { useAppStore } from "@/stores/app-store";
import { cn } from "@/lib/utils";
import { Power, PowerOff, Loader2 } from "lucide-react";
import { api } from "@/lib/api-client";
import { useState } from "react";

export function ConnectionStatus() {
  const systemStatus = useAppStore((s) => s.systemStatus);
  const setReconcileData = useAppStore((s) => s.setReconcileData);
  const setReconcileOpen = useAppStore((s) => s.setReconcileOpen);
  const [loading, setLoading] = useState(false);
  const [loadingPhase, setLoadingPhase] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isRunning = systemStatus?.running ?? false;
  const isReplicating = systemStatus?.replication_active ?? false;

  const handleToggle = async () => {
    setLoading(true);
    setError(null);
    try {
      if (isRunning) {
        await api.stopSystem();
      } else {
        // Phase 1: Connect DAS clients
        setLoadingPhase("Connecting...");
        await api.connectSystem();

        // Phase 2: Check for positions to reconcile
        setLoadingPhase("Checking positions...");
        const reconcileData = await api.getReconciliation();

        if (reconcileData.has_entries) {
          // Show reconciliation modal — it handles apply + start
          setReconcileData(reconcileData);
          setReconcileOpen(true);
        } else {
          // No positions to reconcile — start replication directly
          setLoadingPhase("Starting replication...");
          await api.startReplication();
        }
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to toggle system";
      setError(msg);
      console.error("Failed to toggle system:", e);
    } finally {
      setLoading(false);
      setLoadingPhase(null);
    }
  };

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={handleToggle}
        disabled={loading}
        className={cn(
          "flex items-center gap-2 rounded-md px-4 py-2 text-sm font-semibold transition-colors",
          isRunning
            ? "bg-destructive/10 text-destructive hover:bg-destructive/20"
            : "bg-success/10 text-success hover:bg-success/20",
          loading && "opacity-50 cursor-not-allowed",
        )}
      >
        {loading ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            {loadingPhase ?? "Loading..."}
          </>
        ) : isRunning ? (
          <>
            <PowerOff className="h-4 w-4" />
            Stop
          </>
        ) : (
          <>
            <Power className="h-4 w-4" />
            Start
          </>
        )}
      </button>
      {error && (
        <p className="max-w-xs text-right text-xs text-destructive">{error}</p>
      )}
    </div>
  );
}
