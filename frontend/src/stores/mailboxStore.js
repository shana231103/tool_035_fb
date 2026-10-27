// File: frontend/src/stores/mailboxStore.js
import { defineStore } from 'pinia';
import { mailboxApi } from '../services/api.js';
import { connectionView, mailboxMessage, mailboxReason } from '../services/mailboxConnect.js';

export const createMailboxStoreOptions = (api) => ({
  state: () => ({connections: [], capabilities: null, status: '', error: '', busy: false,
    generation: 0, panelGeneration: 0, pendingId: null, cleanupIds: [], listGeneration: 0}),
  actions: {
    isCurrent(generation) { return generation === this.generation; },
    async openPanel() {
      this.generation++;
      const generation = ++this.panelGeneration;
      this.error = ''; this.status = ''; this.busy = false;
      await Promise.all([this.fetchCapabilities(generation), this.fetchConnections()]);
    },
    closePanel() {
      this.generation++; this.panelGeneration++; this.listGeneration++; this.pendingId = null;
      this.status = ''; this.error = ''; this.busy = false;
    },
    async fetchCapabilities(generation = this.panelGeneration) {
      try {
        const result = await api.capabilities();
        if (generation !== this.panelGeneration) return;
        this.capabilities = {credential_format: result.credential_format,
          template_version: result.template_version, template_label: result.template_label};
      } catch (error) {
        if (generation === this.panelGeneration) { this.capabilities = null; this.error = mailboxMessage(mailboxReason(error)); }
      }
    },
    async fetchConnections() {
      const generation = this.generation, request = ++this.listGeneration;
      try {
        const result = await api.list();
        if (this.isCurrent(generation) && request === this.listGeneration) this.connections = result.map(connectionView);
      } catch (error) { if (this.isCurrent(generation) && request === this.listGeneration) this.error = mailboxMessage(mailboxReason(error)); }
    },
    invalidCredentials() { this.error = mailboxMessage('INVALID_CREDENTIAL_FORMAT'); },
    beginConnect() {
      if (this.busy || this.cleanupIds.length) return null;
      this.busy = true; this.error = ''; this.status = 'CONNECTING';
      return ++this.generation;
    },
    reserved(generation, id) { if (this.isCurrent(generation)) this.pendingId = id; },
    connected(generation, result) {
      if (!this.isCurrent(generation)) return;
      this.listGeneration++;
      this.connections = [...this.connections.filter(item => item.id !== result.id), connectionView(result)];
      this.pendingId = null; this.status = 'CONNECTED';
    },
    connectFailed(generation, reason) {
      if (this.isCurrent(generation)) { this.pendingId = null; this.status = 'FAILED'; this.error = mailboxMessage(reason); }
    },
    finishConnect(generation) { if (this.isCurrent(generation)) this.busy = false; },
    requireCleanup(id) { if (!this.cleanupIds.includes(id)) this.cleanupIds.push(id); },
    confirmCleanup(id) { this.cleanupIds = this.cleanupIds.filter(value => value !== id); },
    cleanupFailed() { this.error = 'Cancellation could not be confirmed. Retry cleanup before connecting again.'; },
    async retryCleanup() {
      if (this.busy) return;
      this.busy = true;
      for (const id of [...this.cleanupIds]) {
        try { await api.disconnect(id); this.confirmCleanup(id); }
        catch { this.cleanupFailed(); }
      }
      if (!this.cleanupIds.length) this.error = '';
      this.busy = false; await this.fetchConnections();
    },
    async saveMapping(id, data) {
      const generation = this.generation;
      this.error = ''; this.busy = true;
      try { await api.map(id, data); if (!this.isCurrent(generation)) return false; await this.fetchConnections(); return true; }
      catch (error) { if (this.isCurrent(generation)) this.error = mailboxMessage(mailboxReason(error)); return false; }
      finally { if (this.isCurrent(generation)) this.busy = false; }
    },
    async disconnect(id) {
      if (this.busy) return;
      const generation = this.generation;
      this.error = ''; this.busy = true;
      try { await api.disconnect(id); if (this.isCurrent(generation)) await this.fetchConnections(); }
      catch (error) { if (this.isCurrent(generation)) this.error = mailboxMessage(mailboxReason(error)); }
      finally { if (this.isCurrent(generation)) this.busy = false; }
    },
  },
});
export const useMailboxStore = defineStore('mailboxes', createMailboxStoreOptions(mailboxApi));
