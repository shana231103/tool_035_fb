// File: frontend/src/stores/browserStore.js
import { defineStore } from 'pinia';
import { browserApi, browserStatusView, browserUnavailable } from '../services/browserStatus.js';
import { wsService } from '../services/websocket.js';

export function createBrowserStoreOptions(api = browserApi, socket = wsService) {
  return {
    state: () => ({status: null, loading: false, error: null, generation: 0, unsubscribe: null}),
    getters: {canStart: state => state.status?.can_start === true && !state.loading && !state.error},
    actions: {
      async refresh(taskId = null) {
        const generation = ++this.generation;
        this.loading = true;
        this.error = null;
        try {
          const status = await api.status(taskId);
          if (generation !== this.generation) return false;
          this.status = browserStatusView(status);
          return true;
        } catch {
          if (generation === this.generation) {
            this.status = null;
            this.error = browserUnavailable;
          }
          return false;
        } finally { if (generation === this.generation) this.loading = false; }
      },
      init() {
        if (!this.unsubscribe) this.unsubscribe = socket.subscribe(event => {
          if (event.type === 'RECONNECTED') void this.refresh();
        });
        return this.refresh();
      },
      stop() {
        ++this.generation;
        this.loading = false;
        this.unsubscribe?.();
        this.unsubscribe = null;
      },
    },
  };
}

export const useBrowserStore = defineStore('browser', createBrowserStoreOptions());
