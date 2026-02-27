"use client";

import { useAppStore } from "@/stores/app-store";
import { AlertTriangle, Info, X } from "lucide-react";

export function AlertsPanel() {
  const alerts = useAppStore((s) => s.alerts);
  const dismissAlert = useAppStore((s) => s.dismissAlert);

  const activeAlerts = alerts.filter((a) => !a.dismissed).slice(0, 10);

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
        {activeAlerts.length === 0 ? (
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
