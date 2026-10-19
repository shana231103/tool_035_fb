// File: frontend/src/stores/browserStore.js
import { defineStore } from 'pinia';
import { browserApi, browserStatusView, browserUnavailable } from '../services/browserStatus.js';
import { wsService } from '../services/websocket.js';
import { authLifecycle } from '../services/authLifecycle.js';

export function createBrowserStoreOptions(api = browserApi, socket = wsService, lifecycle = authLifecycle) {
  return {
    state: () => ({status: null, loading: false, error: null, generation: 0, unsubscribe: null, taskId: null}),
    getters: {canStart: state => state.status?.can_start === true && !state.loading && !state.error},
    actions: {
      async refresh(taskId = this.taskId) {
        const generation = ++this.generation;
        const epoch = lifecycle.currentEpoch;
        this.taskId = taskId;
        this.loading = true;
        this.error = null;
        try {
          const status = await api.status(taskId);
          if (generation !== this.generation || epoch !== lifecycle.currentEpoch) return false;
          this.status = browserStatusView(status);
          return true;
        } catch {
          if (generation === this.generation && epoch === lifecycle.currentEpoch) {
            this.status = null;
            this.error = browserUnavailable;
          }
          return false;
        } finally { if (generation === this.generation && epoch === lifecycle.currentEpoch) this.loading = false; }
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
      resetForAuth(epoch) {
        this.stop();
        this.status = null;
        this.error = null;
        this.taskId = null;
      },
    },
  };
}

export const useBrowserStore = defineStore('browser', createBrowserStoreOptions());
authLifecycle.registerStoreHook({
  resetForAuth(epoch) {try {useBrowserStore().resetForAuth(epoch);} catch {}},
  stop() {try {useBrowserStore().stop();} catch {}},
});
