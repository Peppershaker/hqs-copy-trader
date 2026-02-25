"use client";

import { useAppStore } from "@/stores/app-store";
import { AlertTriangle, Info, X } from "lucide-react";
import { api } from "@/lib/api-client";

export function AlertsPanel() {
  const alerts = useAppStore((s) => s.alerts);
  const dismissAlert = useAppStore((s) => s.dismissAlert);
  const locatePrompts = useAppStore((s) => s.locatePrompts);

  const activeAlerts = alerts.filter((a) => !a.dismissed).slice(0, 10);

  const handleAcceptLocate = async (locateMapId: number) => {
    try {
      await api.acceptLocate(locateMapId);
    } catch (e) {
      console.error("Failed to accept locate:", e);
    }
  };

  const handleRejectLocate = async (locateMapId: number) => {
    try {
      await api.rejectLocate(locateMapId);
    } catch (e) {
      console.error("Failed to reject locate:", e);
    }
  };

  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h3 className="text-sm font-semibold">Alerts</h3>
        {activeAlerts.length > 0 && (
          <span className="rounded-full bg-warning/20 px-2 py-0.5 text-xs font-semibold text-warning">
            {activeAlerts.length}
          </span>
        )}
      </div>

      <div className="max-h-80 overflow-y-auto">
        {/* Locate prompts requiring action */}
        {locatePrompts.map((prompt) => (
          <div
            key={prompt.locate_map_id}
            className="border-b border-border/50 px-4 py-3 bg-warning/5"
          >
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
              <div className="flex-1 text-xs">
                <p className="font-semibold text-warning">Locate Available</p>
                <p className="text-muted-foreground mt-1">
                  {prompt.symbol} on {prompt.follower_id}: $
                  {prompt.follower_price.toFixed(4)}/sh (master: $
                  {prompt.master_price.toFixed(4)}) — {prompt.qty} shares
                </p>
                <div className="mt-2 flex gap-2">
                  <button
                    onClick={() => handleAcceptLocate(prompt.locate_map_id)}
                    className="rounded bg-success/20 px-3 py-1 text-xs font-semibold text-success hover:bg-success/30 transition-colors"
                  >
                    Accept
                  </button>
                  <button
                    onClick={() => handleRejectLocate(prompt.locate_map_id)}
                    className="rounded bg-destructive/20 px-3 py-1 text-xs font-semibold text-destructive hover:bg-destructive/30 transition-colors"
                  >
                    Reject
                  </button>
                </div>
              </div>
            </div>
          </div>
        ))}

        {/* Regular alerts */}
        {activeAlerts.length === 0 && locatePrompts.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-muted-foreground">
            No alerts
          </div>
        ) : (
          activeAlerts.map((alert) => (
            <div
              key={alert.id}
              className="flex items-start gap-2 border-b border-border/50 px-4 py-2.5"
            >
              {alert.type === "error" ? (
                <X className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
              ) : alert.type === "warning" ? (
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
              ) : (
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
              )}
              <p className="flex-1 text-xs text-muted-foreground">
                {alert.message}
              </p>
              <button
                onClick={() => dismissAlert(alert.id)}
                className="shrink-0 text-muted-foreground hover:text-foreground"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
