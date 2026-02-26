/** Global application state using Zustand. */

import { create } from "zustand";
import type {
  Alert,
  Follower,
  LocatePrompt,
  LogEntry,
  MasterConfig,
  OrderInfo,
  Position,
  QueuedAction,
  StateUpdate,
  SystemStatus,
} from "@/lib/types";

interface AppState {
  // Connection
  wsConnected: boolean;
  setWsConnected: (connected: boolean) => void;

  // System status
  systemStatus: SystemStatus | null;

  // Positions
  masterPositions: Position[];
  followerPositions: Record<string, Position[]>;

  // Orders
  masterOrders: OrderInfo[];

  // Configuration (loaded from API)
  masterConfig: MasterConfig | null;
  followers: Follower[];
  setMasterConfig: (config: MasterConfig | null) => void;
  setFollowers: (followers: Follower[]) => void;

  // Alerts
  alerts: Alert[];
  addAlert: (alert: Omit<Alert, "id" | "timestamp">) => void;
  dismissAlert: (id: string) => void;
  clearAlerts: () => void;

  // Locate prompts (active)
  locatePrompts: LocatePrompt[];

  // Queued actions (for disconnected followers)
  queuedActions: Record<string, QueuedAction[]>;
  setQueuedActions: (followerId: string, actions: QueuedAction[]) => void;
  clearQueuedActions: (followerId: string) => void;
  /** follower id that just reconnected with pending actions — triggers dialog */
  replayFollowerId: string | null;
  setReplayFollowerId: (id: string | null) => void;

  // Dev log entries (streamed via WebSocket)
  logEntries: LogEntry[];
  appendLogEntries: (entries: LogEntry[]) => void;
  clearLogEntries: () => void;

  // Update from WebSocket state_update
  handleStateUpdate: (data: StateUpdate) => void;

  // Handle specific WS messages
  handleWSMessage: (type: string, data: Record<string, unknown>) => void;
}

let alertCounter = 0;

export const useAppStore = create<AppState>((set, get) => ({
  wsConnected: false,
  setWsConnected: (connected) => set({ wsConnected: connected }),

  systemStatus: null,
  masterPositions: [],
  followerPositions: {},
  masterOrders: [],

  masterConfig: null,
  followers: [],
  setMasterConfig: (config) => set({ masterConfig: config }),
  setFollowers: (followers) => set({ followers }),

  alerts: [],
  addAlert: (alert) => {
    const id = `alert-${++alertCounter}`;
    set((state) => ({
      alerts: [{ ...alert, id, timestamp: Date.now() }, ...state.alerts].slice(
        0,
        50,
      ), // Keep max 50 alerts
    }));
  },
  dismissAlert: (id) =>
    set((state) => ({
      alerts: state.alerts.map((a) =>
        a.id === id ? { ...a, dismissed: true } : a,
      ),
    })),
  clearAlerts: () => set({ alerts: [] }),

  locatePrompts: [],

  queuedActions: {},
  setQueuedActions: (followerId, actions) =>
    set((s) => ({
      queuedActions: { ...s.queuedActions, [followerId]: actions },
    })),
  clearQueuedActions: (followerId) =>
    set((s) => {
      const next = { ...s.queuedActions };
      delete next[followerId];
      return { queuedActions: next };
    }),
  replayFollowerId: null,
  setReplayFollowerId: (id) => set({ replayFollowerId: id }),

  logEntries: [],
  appendLogEntries: (entries) =>
    set((s) => ({
      logEntries: [...s.logEntries, ...entries].slice(-2000),
    })),
  clearLogEntries: () => set({ logEntries: [] }),

  handleStateUpdate: (data) => {
    set({
      systemStatus: data.status,
      masterPositions: data.positions?.master || [],
      followerPositions: data.positions?.followers || {},
      masterOrders: data.master_orders || [],
    });
  },

  handleWSMessage: (type, data) => {
    const state = get();

    switch (type) {
      case "state_update":
        state.handleStateUpdate(data as unknown as StateUpdate);
        break;

      case "order_replicated":
        state.addAlert({
          type: "info",
          message: `Order replicated: ${data.side} ${data.quantity} ${data.symbol}`,
          data,
        });
        break;

      case "locate_prompt":
        set((s) => ({
          locatePrompts: [...s.locatePrompts, data as unknown as LocatePrompt],
        }));
        state.addAlert({
          type: "locate_prompt",
          message: `Locate available for ${data.symbol} on ${data.follower_id}: $${data.follower_price}/sh (master: $${data.master_price}/sh)`,
          data,
        });
        break;

      case "locate_found":
        state.addAlert({
          type: "info",
          message: `Locates found for ${data.symbol} on ${data.follower_id}`,
          data,
        });
        break;

      case "locate_accepted_manual_entry":
        state.addAlert({
          type: "warning",
          message: String(data.message),
          data,
        });
        // Remove from prompts
        set((s) => ({
          locatePrompts: s.locatePrompts.filter(
            (p) => p.locate_map_id !== data.locate_map_id,
          ),
        }));
        break;

      case "locate_rejected":
        set((s) => ({
          locatePrompts: s.locatePrompts.filter(
            (p) => p.locate_map_id !== data.locate_map_id,
          ),
        }));
        state.addAlert({
          type: "info",
          message: `Locate rejected for ${data.symbol} on ${data.follower_id}. Symbol blacklisted.`,
          data,
        });
        break;

      case "multiplier_inferred":
        state.addAlert({
          type: "multiplier_inferred",
          message: `Auto-adjusted multiplier for ${data.follower_id} on ${data.symbol}: ${data.old_multiplier}× → ${data.new_multiplier}×`,
          data,
        });
        break;

      case "alert":
        state.addAlert({
          type:
            data.level === "error"
              ? "error"
              : data.level === "warn"
                ? "warning"
                : "info",
          message: String(data.message),
          data,
        });
        break;

      case "buying_power_warning":
        state.addAlert({
          type: "warning",
          message: `Buying power warning on ${data.follower_id}: available $${data.available}, required $${data.required}`,
          data,
        });
        break;

      case "action_queued":
        state.addAlert({
          type: "warning",
          message: String(data.message),
          data,
        });
        break;

      case "queued_actions_available": {
        const fid = String(data.follower_id);
        const actions = (data.actions ?? []) as unknown as QueuedAction[];
        set((s) => ({
          queuedActions: { ...s.queuedActions, [fid]: actions },
          replayFollowerId: fid,
        }));
        state.addAlert({
          type: "warning",
          message: `Follower ${fid} reconnected with ${actions.length} queued action(s) — review and replay`,
          data,
        });
        break;
      }

      case "actions_replayed":
        state.addAlert({
          type: "info",
          message: `Replayed actions on ${data.follower_id}`,
          data,
        });
        state.clearQueuedActions(String(data.follower_id));
        break;

      case "log_entries":
        state.appendLogEntries(
          (data.entries ?? []) as unknown as LogEntry[],
        );
        break;
    }
  },
}));
