import { WebSocketEventPayload } from "../types/chat";

type ConnectionState = "idle" | "connecting" | "open" | "closed";

type ChatSocketCallbacks = {
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (message: string) => void;
  onEvent?: (payload: WebSocketEventPayload) => void;
};

export class ChatSocketClient {
  private socket: WebSocket | null = null;
  private state: ConnectionState = "idle";
  private lastUrl: string | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempt = 0;
  private intentionallyClosed = false;

  /** Max delay between reconnect attempts (ms). */
  private static readonly MAX_DELAY_MS = 10_000;
  /** Base delay for exponential backoff (ms). */
  private static readonly BASE_DELAY_MS = 1_000;

  constructor(private readonly callbacks: ChatSocketCallbacks) {}

  connect(url: string): void {
    // If already open/connecting to the same URL, skip.
    if (this.socket && (this.state === "connecting" || this.state === "open")) {
      return;
    }

    this.intentionallyClosed = false;
    this.lastUrl = url;
    this.state = "connecting";
    this.socket = new WebSocket(url);

    this.socket.onopen = () => {
      this.state = "open";
      this.reconnectAttempt = 0;
      this.clearReconnectTimer();
      this.callbacks.onOpen?.();
    };

    this.socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(String(event.data)) as WebSocketEventPayload;
        this.callbacks.onEvent?.(payload);
      } catch (_error) {
        this.callbacks.onError?.("Received invalid event from server.");
      }
    };

    this.socket.onerror = () => {
      this.callbacks.onError?.("WebSocket connection error.");
    };

    this.socket.onclose = () => {
      this.state = "closed";
      this.callbacks.onClose?.();
      // Auto-reconnect unless intentionally closed.
      if (!this.intentionallyClosed && this.lastUrl) {
        this.scheduleReconnect();
      }
    };
  }

  sendMessage(accessToken: string, message: string, userId?: number): boolean {
    if (!this.socket || this.state !== "open") {
      return false;
    }

    const token = String(accessToken || "").trim();
    if (!token) {
      return false;
    }

    this.socket.send(
      JSON.stringify({
        access_token: token,
        user_id: userId,
        message,
      }),
    );
    return true;
  }

  close(): void {
    this.intentionallyClosed = true;
    this.clearReconnectTimer();
    this.reconnectAttempt = 0;
    this.socket?.close();
    this.socket = null;
    this.state = "closed";
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer || this.intentionallyClosed || !this.lastUrl) {
      return;
    }
    this.reconnectAttempt += 1;
    const delay = Math.min(
      ChatSocketClient.BASE_DELAY_MS * Math.pow(1.5, this.reconnectAttempt - 1),
      ChatSocketClient.MAX_DELAY_MS,
    );
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (!this.intentionallyClosed && this.lastUrl) {
        this.connect(this.lastUrl);
      }
    }, delay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}
