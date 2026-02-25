"use client";

import { useEffect, useRef } from "react";
import { getWSClient } from "@/lib/ws-client";
import { useAppStore } from "@/stores/app-store";

/**
 * Hook that manages the WebSocket connection lifecycle.
 * Should be called once in the root layout.
 */
export function useWebSocket() {
  const handleWSMessage = useAppStore((s) => s.handleWSMessage);
  const setWsConnected = useAppStore((s) => s.setWsConnected);
  const clientRef = useRef(getWSClient());

  useEffect(() => {
    const client = clientRef.current;

    const unsub = client.onMessage((msg) => {
      handleWSMessage(msg.type, msg.data);
    });

    // Poll connection state
    const interval = setInterval(() => {
      setWsConnected(client.isConnected);
    }, 1000);

    client.connect();

    return () => {
      unsub();
      clearInterval(interval);
      client.disconnect();
    };
  }, [handleWSMessage, setWsConnected]);

  return clientRef.current;
}