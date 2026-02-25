"use client";

import { useWebSocket } from "@/hooks/use-websocket";

/**
 * Wrapper that initializes the WebSocket connection.
 * Used in the root layout to enable global real-time updates.
 */
export function WSProvider({ children }: { children: React.ReactNode }) {
  useWebSocket();
  return <>{children}</>;
}