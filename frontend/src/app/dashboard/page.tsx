"use client";

import { useAppStore } from "@/stores/app-store";
import { PositionsTable } from "@/components/dashboard/positions-table";
import { AlertsPanel } from "@/components/dashboard/alerts-panel";
import { ConnectionStatus } from "@/components/dashboard/connection-status";

export default function DashboardPage() {
  const masterPositions = useAppStore((s) => s.masterPositions);
  const followerPositions = useAppStore((s) => s.followerPositions);
  const followers = useAppStore((s) => s.followers);
  const systemStatus = useAppStore((s) => s.systemStatus);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Real-time overview of all accounts
          </p>
        </div>
        <ConnectionStatus />
      </div>

      {/* Master positions */}
      <PositionsTable positions={masterPositions} title="Master Account" />

      {/* Follower positions */}
      {Object.entries(followerPositions).map(([followerId, positions]) => {
        const follower = followers.find((f) => f.id === followerId);
        const connected = systemStatus?.followers?.[followerId]?.connected;
        const name = follower?.name || followerId;
        const multiplier = follower?.base_multiplier ?? 1;

        return (
          <PositionsTable
            key={followerId}
            positions={positions}
            title={`${name} (${multiplier}×) ${connected ? "●" : "○"}`}
            showMultiplier
          />
        );
      })}

      {/* Alerts */}
      <AlertsPanel />
    </div>
  );
}