"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Heart,
  Activity,
  Clock,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Wifi,
  WifiOff,
  Zap,
  BarChart3,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import type {
  HealthResponse,
  AccountDiagnostics,
  ServerState,
  HeartbeatStatus,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function healthColor(level: string): string {
  switch (level) {
    case "healthy":
      return "text-success";
    case "degraded":
      return "text-warning";
    case "critical":
      return "text-destructive";
    default:
      return "text-muted-foreground";
  }
}

function healthBg(level: string): string {
  switch (level) {
    case "healthy":
      return "bg-success/10 border-success/30";
    case "degraded":
      return "bg-warning/10 border-warning/30";
    case "critical":
      return "bg-destructive/10 border-destructive/30";
    default:
      return "bg-muted/50 border-border";
  }
}

function statusDot(status: string): string {
  switch (status) {
    case "connected":
      return "bg-success";
    case "disconnected":
      return "bg-destructive";
    default:
      return "bg-muted-foreground";
  }
}

function heartbeatDot(health: string): string {
  switch (health) {
    case "healthy":
      return "bg-success";
    case "degraded":
      return "bg-warning";
    case "critical":
      return "bg-destructive";
    default:
      return "bg-muted-foreground";
  }
}

function HealthIcon({ level }: { level: string }) {
  switch (level) {
    case "healthy":
      return <CheckCircle2 className="h-5 w-5 text-success" />;
    case "degraded":
      return <AlertTriangle className="h-5 w-5 text-warning" />;
    case "critical":
      return <XCircle className="h-5 w-5 text-destructive" />;
    default:
      return <Heart className="h-5 w-5 text-muted-foreground" />;
  }
}

function formatUptime(seconds: number): string {
  if (seconds <= 0) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m}m ${s}s`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return "Never";
  const d = new Date(iso);
  return d.toLocaleTimeString();
}

function formatSeconds(val: number | null | undefined): string {
  if (val == null) return "—";
  return `${val.toFixed(1)}s`;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ServerStatusCard({
  label,
  icon: Icon,
  state,
}: {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  state: ServerState;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium">{label}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className={cn("h-2.5 w-2.5 rounded-full", statusDot(state.status))} />
          <span
            className={cn(
              "text-xs font-semibold uppercase tracking-wide",
              state.status === "connected"
                ? "text-success"
                : state.status === "disconnected"
                  ? "text-destructive"
                  : "text-muted-foreground",
            )}
          >
            {state.status}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <div className="text-muted-foreground">Last Connected</div>
        <div className="text-right font-mono">{formatTimestamp(state.last_connected)}</div>

        <div className="text-muted-foreground">Last Disconnected</div>
        <div className="text-right font-mono">
          {formatTimestamp(state.last_disconnected)}
        </div>

        <div className="text-muted-foreground">Connects</div>
        <div className="text-right font-mono">{state.connect_count}</div>

        <div className="text-muted-foreground">Disconnects</div>
        <div className="text-right font-mono">{state.disconnect_count}</div>

        {state.last_error && (
          <>
            <div className="text-muted-foreground col-span-2 pt-1">Last Error</div>
            <div className="text-destructive col-span-2 break-all">{state.last_error}</div>
          </>
        )}
      </div>
    </div>
  );
}

function HeartbeatCard({ heartbeat }: { heartbeat: HeartbeatStatus }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium">Heartbeat</span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "h-2.5 w-2.5 rounded-full",
              heartbeatDot(heartbeat.health),
              heartbeat.health === "healthy" && "animate-pulse",
            )}
          />
          <span
            className={cn(
              "text-xs font-semibold uppercase tracking-wide",
              heartbeat.health === "healthy"
                ? "text-success"
                : heartbeat.health === "degraded"
                  ? "text-warning"
                  : heartbeat.health === "critical"
                    ? "text-destructive"
                    : "text-muted-foreground",
            )}
          >
            {heartbeat.health}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <div className="text-muted-foreground">Since Last Sent</div>
        <div className="text-right font-mono">
          {formatSeconds(heartbeat.seconds_since_heartbeat_sent)}
        </div>

        <div className="text-muted-foreground">Since Last Recv</div>
        <div className="text-right font-mono">
          {formatSeconds(heartbeat.seconds_since_heartbeat_recv)}
        </div>

        <div className="text-muted-foreground">Degraded Threshold</div>
        <div className="text-right font-mono">
          {formatSeconds(heartbeat.degraded_threshold)}
        </div>

        <div className="text-muted-foreground">Critical Threshold</div>
        <div className="text-right font-mono">
          {formatSeconds(heartbeat.critical_threshold)}
        </div>
      </div>
    </div>
  );
}

function ManagerStatus({ label, running }: { label: string; running: boolean }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span
        className={cn(
          "text-xs font-medium",
          running ? "text-success" : "text-muted-foreground",
        )}
      >
        {running ? "Running" : "Stopped"}
      </span>
    </div>
  );
}

function MetricItem({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-xs font-mono">{value}</span>
    </div>
  );
}

function AccountHealthCard({
  title,
  diag,
}: {
  title: string;
  diag: AccountDiagnostics;
}) {
  if (diag.error) {
    return (
      <div className="rounded-xl border border-border bg-card p-5">
        <h3 className="text-sm font-semibold mb-3">{title}</h3>
        <p className="text-xs text-destructive">{diag.error}</p>
      </div>
    );
  }

  const { health, metrics } = diag;
  const uptime = metrics?.overall?.uptime_seconds ?? 0;

  // Extract key order metrics
  const orderMetrics = metrics?.orders ?? {};
  const tradeMetrics = metrics?.trades ?? {};
  const positionMetrics = metrics?.positions ?? {};

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      {/* Account header with health level */}
      <div
        className={cn(
          "flex items-center justify-between px-5 py-3 border-b",
          healthBg(health.health_level),
        )}
      >
        <div className="flex items-center gap-2">
          <HealthIcon level={health.health_level} />
          <h3 className="text-sm font-semibold">{title}</h3>
        </div>
        <div className="flex items-center gap-3">
          {uptime > 0 && (
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Clock className="h-3 w-3" />
              {formatUptime(uptime)}
            </div>
          )}
          <span
            className={cn(
              "text-xs font-bold uppercase tracking-wider",
              healthColor(health.health_level),
            )}
          >
            {health.health_level}
          </span>
        </div>
      </div>

      <div className="p-5 space-y-5">
        {/* Server statuses - 2x2 grid */}
        <div>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
            Server Connections
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <ServerStatusCard label="API Server" icon={Wifi} state={health.api_server} />
            <ServerStatusCard
              label="Order Server"
              icon={Zap}
              state={health.order_server}
            />
            <ServerStatusCard
              label="Quote Server"
              icon={BarChart3}
              state={health.quote_server}
            />
            <HeartbeatCard heartbeat={health.heartbeat} />
          </div>
        </div>

        {/* Managers + Metrics side by side */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Internal managers */}
          <div className="rounded-lg border border-border bg-card p-4">
            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
              Internal Managers
            </h4>
            <div className="divide-y divide-border">
              <ManagerStatus label="Order Manager" running={health.order_manager} />
              <ManagerStatus label="Trade Manager" running={health.trade_manager} />
              <ManagerStatus label="Position Manager" running={health.position_manager} />
              <ManagerStatus
                label="Market Data Manager"
                running={health.market_data_manager}
              />
              <ManagerStatus
                label="Short Locate Manager"
                running={health.short_locate_manager}
              />
              <ManagerStatus label="Health Monitor" running={health.health_monitor} />
            </div>
          </div>

          {/* Key metrics */}
          <div className="rounded-lg border border-border bg-card p-4">
            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
              Key Metrics
            </h4>
            <div className="divide-y divide-border">
              {/* Orders */}
              <MetricItem
                label="Orders Submitted"
                value={safeMetric(orderMetrics, "orders_submitted", "total_submitted")}
              />
              <MetricItem
                label="Orders Filled"
                value={safeMetric(orderMetrics, "orders_filled", "total_filled")}
              />
              <MetricItem
                label="Orders Cancelled"
                value={safeMetric(orderMetrics, "orders_cancelled", "total_cancelled")}
              />
              <MetricItem
                label="Orders Rejected"
                value={safeMetric(orderMetrics, "orders_rejected", "total_rejected")}
              />
              {/* Trades */}
              <MetricItem
                label="Total Trades"
                value={safeMetric(tradeMetrics, "total_trades", "trades_processed")}
              />
              {/* Positions */}
              <MetricItem
                label="Open Positions"
                value={safeMetric(positionMetrics, "open_positions", "total_positions")}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Safely extract a metric value trying multiple key names. */
function safeMetric(
  obj: Record<string, unknown>,
  ...keys: string[]
): string | number {
  for (const key of keys) {
    if (key in obj && obj[key] != null) {
      return String(obj[key]);
    }
  }
  return "—";
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function HealthPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getHealth();
      setHealth(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial fetch + auto refresh every 5s
  useEffect(() => {
    fetchHealth();
    if (!autoRefresh) return;
    const interval = setInterval(fetchHealth, 5000);
    return () => clearInterval(interval);
  }, [fetchHealth, autoRefresh]);

  // Overall health level derived from all accounts
  const overallHealth = deriveOverallHealth(health);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">System Health</h1>
          <p className="text-sm text-muted-foreground">
            Detailed diagnostics for all DAS connections
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setAutoRefresh((v) => !v)}
            className={cn(
              "text-xs px-3 py-1.5 rounded-md border transition-colors",
              autoRefresh
                ? "border-success/30 text-success bg-success/10"
                : "border-border text-muted-foreground bg-card hover:bg-muted",
            )}
          >
            {autoRefresh ? "Auto-refresh ON" : "Auto-refresh OFF"}
          </button>
          <button
            onClick={fetchHealth}
            disabled={loading}
            className={cn(
              "flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md border border-border bg-card text-muted-foreground hover:bg-muted transition-colors",
              loading && "opacity-50 cursor-not-allowed",
            )}
          >
            <RefreshCw className={cn("h-3 w-3", loading && "animate-spin")} />
            Refresh
          </button>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Overall health banner */}
      {health && (
        <div
          className={cn(
            "rounded-xl border p-4 flex items-center justify-between",
            healthBg(overallHealth),
          )}
        >
          <div className="flex items-center gap-3">
            <HealthIcon level={overallHealth} />
            <div>
              <div className="text-sm font-semibold">
                Overall System:{" "}
                <span className={healthColor(overallHealth)}>
                  {overallHealth.toUpperCase()}
                </span>
              </div>
              <div className="text-xs text-muted-foreground">
                {health.running
                  ? `${1 + Object.keys(health.followers).length} account(s) monitored`
                  : "System not running"}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {health.running ? (
              <Wifi className="h-4 w-4 text-success" />
            ) : (
              <WifiOff className="h-4 w-4 text-muted-foreground" />
            )}
          </div>
        </div>
      )}

      {/* Not running / no data */}
      {health && !health.running && (
        <div className="text-center py-12 text-muted-foreground text-sm">
          <WifiOff className="h-8 w-8 mx-auto mb-3 opacity-50" />
          <p>System is not running. Start the system to view health diagnostics.</p>
        </div>
      )}

      {/* Account cards */}
      {health?.running && (
        <div className="space-y-6">
          {/* Master */}
          {health.master && (
            <AccountHealthCard title="Master Account" diag={health.master} />
          )}

          {/* Followers */}
          {Object.entries(health.followers).map(([fid, diag]) => (
            <AccountHealthCard key={fid} title={`Follower: ${fid}`} diag={diag} />
          ))}
        </div>
      )}

      {/* Loading skeleton when no data */}
      {!health && !error && (
        <div className="space-y-4">
          {[1, 2].map((i) => (
            <div
              key={i}
              className="h-64 rounded-xl border border-border bg-card animate-pulse"
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** Derive worst overall health across all accounts. */
function deriveOverallHealth(health: HealthResponse | null): string {
  if (!health || !health.running) return "unknown";

  const levels: string[] = [];
  if (health.master?.health) {
    levels.push(health.master.health.health_level);
  }
  for (const diag of Object.values(health.followers)) {
    if (diag?.health) {
      levels.push(diag.health.health_level);
    }
  }

  if (levels.length === 0) return "unknown";
  if (levels.includes("critical")) return "critical";
  if (levels.includes("degraded")) return "degraded";
  return "healthy";
}
