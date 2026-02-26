/** Shared TypeScript types that match the backend Pydantic schemas. */

// --- Account types ---

export interface MasterConfig {
  id: number;
  broker_id: string;
  host: string;
  port: number;
  username: string;
  account_id: string;
  locate_routes?: Record<string, number> | null;
  updated_at: string;
}

export interface MasterConfigCreate {
  broker_id: string;
  host: string;
  port: number;
  username: string;
  password: string;
  account_id: string;
  locate_routes?: Record<string, number> | null;
}

export interface Follower {
  id: string;
  name: string;
  broker_id: string;
  host: string;
  port: number;
  username: string;
  account_id: string;
  base_multiplier: number;
  max_locate_price_delta: number;
  locate_retry_timeout: number;
  auto_accept_locates: boolean;
  enabled: boolean;
  locate_routes?: Record<string, number> | null;
  created_at: string;
  updated_at: string;
}

export interface FollowerCreate {
  id: string;
  name: string;
  broker_id: string;
  host: string;
  port: number;
  username: string;
  password: string;
  account_id: string;
  base_multiplier?: number;
  max_locate_price_delta?: number;
  locate_retry_timeout?: number;
  auto_accept_locates?: boolean;
  enabled?: boolean;
  locate_routes?: Record<string, number> | null;
}

// --- Position types ---

export interface Position {
  symbol: string;
  side: string;
  quantity: number;
  avg_cost: number;
  realized_pnl: number;
  unrealized_pnl: number;
  total_pnl: number;
  last_price: number;
  effective_multiplier?: number;
  multiplier_source?: string;
}

// --- Order types ---

export interface OrderInfo {
  order_id: number;
  token: number;
  symbol: string;
  side: string;
  quantity: number;
  status: string;
}

// --- Blacklist ---

export interface BlacklistEntry {
  id: number;
  follower_id: string;
  symbol: string;
  reason: string | null;
  created_at: string;
}

// --- Symbol Multiplier ---

export interface SymbolMultiplier {
  id: number;
  follower_id: string;
  symbol: string;
  multiplier: number;
  source: string;
  updated_at: string;
}

// --- Locate ---

export interface LocatePrompt {
  locate_map_id: number;
  follower_id: string;
  symbol: string;
  qty: number;
  master_price: number;
  follower_price: number;
  reason: string;
}

// --- WebSocket Messages ---

export type WSMessageType =
  | "state_update"
  | "order_replicated"
  | "order_cancelled"
  | "order_replaced"
  | "locate_prompt"
  | "locate_found"
  | "locate_accepted"
  | "locate_accepted_manual_entry"
  | "locate_rejected"
  | "multiplier_inferred"
  | "alert"
  | "buying_power_warning"
  | "action_queued"
  | "queued_actions_available"
  | "actions_replayed";

export interface WSMessage {
  type: WSMessageType;
  data: Record<string, unknown>;
}

// --- System Status ---

export interface SystemStatus {
  running: boolean;
  master: {
    configured: boolean;
    connected: boolean;
  };
  followers: Record<
    string,
    {
      connected: boolean;
    }
  >;
}

// --- State Update (from WebSocket) ---

export interface StateUpdate {
  status: SystemStatus;
  positions: {
    master: Position[];
    followers: Record<string, Position[]>;
  };
  master_orders: OrderInfo[];
}

// --- Alert ---

export interface Alert {
  id: string;
  type: "locate_prompt" | "multiplier_inferred" | "error" | "info" | "warning";
  message: string;
  data?: Record<string, unknown>;
  timestamp: number;
  dismissed?: boolean;
}

// --- Audit Log ---

export interface AuditLogEntry {
  id: number;
  timestamp: string;
  level: string;
  category: string;
  follower_id: string | null;
  symbol: string | null;
  message: string;
  details: string | null;
}

// --- DAS Bridge Server Config ---

export interface DasServer {
  broker_id: string;
  host: string;
  port: number;
  username: string;
  password: string;
  accounts: string[];
  smart_routes: string[];
  locate_routes: Record<string, number>;
}

// --- Queued Action (disconnected follower) ---

export interface QueuedAction {
  id: string;
  follower_id: string;
  action_type: "order_submit" | "order_cancel" | "order_replace" | "locate";
  symbol: string;
  timestamp: number;
  payload: Record<string, unknown>;
}

// --- Env Config ---

export interface EnvConfigResponse {
  content: string;
  updated_at: string | null;
  parsed_keys: string[];
}

// --- Health / Diagnostics ---

export interface ServerState {
  status: "unknown" | "connected" | "disconnected";
  is_connected: boolean;
  last_connected: string | null;
  last_disconnected: string | null;
  connect_count: number;
  disconnect_count: number;
  last_error: string | null;
}

export interface HeartbeatStatus {
  health: "healthy" | "degraded" | "critical" | "unknown";
  last_heartbeat_sent_time: number;
  seconds_since_heartbeat_sent: number | null;
  last_heartbeat_recv_time: number | null;
  seconds_since_heartbeat_recv: number | null;
  degraded_threshold: number;
  critical_threshold: number;
}

export interface AccountHealth {
  health_level: "healthy" | "degraded" | "critical";
  connection: boolean;
  api_server: ServerState;
  quote_server: ServerState;
  order_server: ServerState;
  heartbeat: HeartbeatStatus;
  is_fully_connected: boolean;
  order_manager: boolean;
  trade_manager: boolean;
  position_manager: boolean;
  market_data_manager: boolean;
  short_locate_manager: boolean;
  health_monitor: boolean;
  market_data_subscriptions_within_limit: boolean;
}

export interface AccountMetrics {
  orders: Record<string, unknown>;
  trades: Record<string, unknown>;
  positions: Record<string, unknown>;
  market_data: Record<string, unknown>;
  short_locates: Record<string, unknown>;
  overall: {
    is_running: boolean;
    uptime_seconds: number;
    start_time: string | null;
  };
}

export interface AccountDiagnostics {
  health: AccountHealth;
  metrics: AccountMetrics;
  error?: string;
}

export interface HealthResponse {
  running: boolean;
  master: AccountDiagnostics | null;
  followers: Record<string, AccountDiagnostics>;
}
