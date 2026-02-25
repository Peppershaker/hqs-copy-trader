/** Shared TypeScript types that match the backend Pydantic schemas. */

// --- Account types ---

export interface MasterConfig {
  id: number;
  broker_id: string;
  host: string;
  port: number;
  username: string;
  account_id: string;
  locate_routes?: Record<string, unknown>[] | null;
  updated_at: string;
}

export interface MasterConfigCreate {
  broker_id: string;
  host: string;
  port: number;
  username: string;
  password: string;
  account_id: string;
  locate_routes?: Record<string, unknown>[] | null;
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
  locate_routes?: Record<string, unknown>[] | null;
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
  locate_routes?: Record<string, unknown>[] | null;
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
