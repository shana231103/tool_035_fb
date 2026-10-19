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
    if (typeof window === "undefined") {
      return;
    }
    if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws`;

    const socket = new WebSocket(wsUrl);
    this.socket = socket;

    this.socket.onopen = () => {
      if (this.socket !== socket || this.stopped) return;
      this.isConnected = true;
      this.subscribers.forEach(cb => cb({type:"RECONNECTED"}));
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = null;
      }
    };

    this.socket.onmessage = (event) => {
      if (this.socket !== socket || this.stopped) return;
      try {
        if (typeof event.data !== 'string' || event.data.length > 65536) return;
        const data = JSON.parse(event.data);
        this.subscribers.forEach((cb) => cb(data));
      } catch (err) {
        // Invalid events cannot change authoritative HTTP snapshots.
      }
    };

    this.socket.onclose = () => {
      if (this.socket !== socket) return;
      this.isConnected = false;
      if (!this.stopped) this.reconnectTimer = setTimeout(() => this.connect(), 3000);
    };

    this.socket.onerror = () => {
      if (this.socket === socket) socket.close();
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
      this.reconnectTimer = null;
    }
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
    this.isConnected = false;
  }
}

export const wsService = new RealtimeWebSocketService();
