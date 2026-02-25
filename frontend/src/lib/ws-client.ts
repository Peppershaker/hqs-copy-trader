/** WebSocket client with auto-reconnect. */

type MessageHandler = (message: {
  type: string;
  data: Record<string, unknown>;
}) => void;

export class WSClient {
  private ws: WebSocket | null = null;
  private url: string;
  private handlers: Set<MessageHandler> = new Set();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectDelay = 1000;
  private maxReconnectDelay = 30000;
  private shouldReconnect = true;

  constructor(url?: string) {
    // In production the frontend is served by the backend on the same port.
    // In dev the backend is always on NEXT_PUBLIC_WS_PORT (default 8787).
    // Do NOT fall back to window.location.port — in dev that would be 3000.
    const wsPort = process.env.NEXT_PUBLIC_WS_PORT || "8787";
    const wsBase =
      typeof window !== "undefined"
        ? `ws://${window.location.hostname}:${wsPort}`
        : "ws://127.0.0.1:8787";
    this.url = url || `${wsBase}/ws`;
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        console.log("[WS] Connected");
        this.reconnectDelay = 1000; // Reset on successful connect
      };

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          this.handlers.forEach((handler) => handler(message));
        } catch (e) {
          console.error("[WS] Parse error:", e);
        }
      };

      this.ws.onclose = () => {
        console.log("[WS] Disconnected");
        if (this.shouldReconnect) {
          this.scheduleReconnect();
        }
      };

      this.ws.onerror = (error) => {
        console.error("[WS] Error:", error);
      };
    } catch (e) {
      console.error("[WS] Connection failed:", e);
      this.scheduleReconnect();
    }
  }

  disconnect(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  send(action: string, data?: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action, ...data }));
    }
  }

  onMessage(handler: MessageHandler): () => void {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    console.log(`[WS] Reconnecting in ${this.reconnectDelay}ms...`);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.reconnectDelay = Math.min(
        this.reconnectDelay * 2,
        this.maxReconnectDelay,
      );
      this.connect();
    }, this.reconnectDelay);
  }
}

// Singleton
let _client: WSClient | null = null;

export function getWSClient(): WSClient {
  if (!_client) {
    _client = new WSClient();
  }
  return _client;
}
