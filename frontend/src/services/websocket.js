// File: frontend/src/services/websocket.js
class RealtimeWebSocketService {
  constructor() {
    this.socket = null;
    this.subscribers = new Set();
    this.reconnectTimer = null;
    this.isConnected = false;
    this.stopped = false;
  }

  connect() {
    this.stopped = false;
    if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws`;

    this.socket = new WebSocket(wsUrl);

    this.socket.onopen = () => {
      this.isConnected = true;
      this.subscribers.forEach(cb => cb({type:"RECONNECTED"}));
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = null;
      }
    };

    this.socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.subscribers.forEach((cb) => cb(data));
      } catch (err) {
        console.error("Failed to parse WebSocket JSON payload:", err);
      }
    };

    this.socket.onclose = () => {
      this.isConnected = false;
      if (!this.stopped) this.reconnectTimer = setTimeout(() => this.connect(), 3000);
    };

    this.socket.onerror = (err) => {
      console.error("WebSocket encountered an error:", err);
      this.socket?.close();
    };
  }

  subscribe(callback) {
    this.subscribers.add(callback);
    return () => {
      this.subscribers.delete(callback);
    };
  }

  disconnect() {
    this.stopped = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    this.isConnected = false;
  }
}

export const wsService = new RealtimeWebSocketService();
