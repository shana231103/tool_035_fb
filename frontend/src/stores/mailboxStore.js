// File: frontend/src/stores/mailboxStore.js
import { defineStore } from 'pinia';
import { mailboxApi } from '../services/api.js';

const connectionView = (item) => ({id:item.id, status:item.status, masked_email:item.masked_email,
  mapped_email_masked:item.mapped_email_masked, expires_at:item.expires_at, safe_reason:item.safe_reason});
const reasons = {
  CONFIGURATION_REQUIRED: 'Enter and apply your Microsoft application ID in this panel before connecting.',
  CONSENT_REQUIRED: 'Microsoft permission to read mail is required. Reconnect and review consent.',
  MAIL_READ_REQUIRED: 'Microsoft sign-in succeeded, but its token does not include Microsoft Graph Mail.Read. Configure this tool’s own Microsoft application with delegated User.Read and Mail.Read, then reconnect.',
  APP_CONSENT_REQUIRED: 'Microsoft did not issue a token for this application because consent is required. Check the application registration and permissions, then reconnect.',
  GRAPH_ACCESS_DENIED: 'Microsoft sign-in succeeded, but Graph denied mailbox access. Check this application’s delegated Graph permissions and account support.',
  GRAPH_AUTH_REJECTED: 'Microsoft Graph rejected the sign-in token. Check this application’s Graph scopes and reconnect.',
  MAILBOX_NOT_SUPPORTED: 'This Microsoft mailbox is not enabled or supported for Graph mail access. Check the account’s mailbox availability.',
  EVIDENCE_REQUIRED: 'This mail template is not supported. Choose the provided Meta report template.',
  MAPPING_INVALID: 'Use the authenticated mailbox email. Aliases require separate delivery verification.',
  AUTH_REQUIRED: 'Sign in to Microsoft again before starting a report.',
  GRAPH_PROTOCOL_ERROR: 'Microsoft returned an unsupported sign-in response. Update or restart the backend and try again.',
  MAILBOX_UNAVAILABLE: 'Microsoft mailbox is unavailable. Check the connection and try again.',
  DISCONNECTED: 'The mailbox session was disconnected. Restart the backend if it has shut down, then connect again.',
  LOGIN_EXPIRED: 'Microsoft login expired. Start a new login.',
  LOGIN_CANCELLED: 'Microsoft login was cancelled. Start a new login when ready.',
  BUSY: 'This connection is busy. Stop its active report before changing the mailbox.',
};
const safeFailure = (error) => reasons[error.response?.data?.detail] || (error.response?.status === 409
  ? 'Connection is busy, conflicting, or the evidence profile is not ready. Stop active attempts before changing mapping.'
  : 'Microsoft mailbox action failed. Check consent and connection status.');

export const createMailboxStoreOptions = (mailboxApi) => ({
  state: () => ({connections:[], configuration:null, prompt:null, loginStatus:'', error:'', busy:false,
    pollTimer:null, generation:0, loginId:null}),
  actions: {
    async fetchConfiguration() {
      try {
        const result = await mailboxApi.configuration();
        this.configuration = {login_configured:result.login_configured === true, client_id:result.client_id || '',
          template_version:result.template_version, template_label:result.template_label};
      } catch (error) { this.configuration = null; this.error = safeFailure(error); }
    },
    async configureClient(clientId) {
      if (this.busy) return false;
      const value = clientId.trim();
      if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)) {
        this.error = 'Enter a valid Microsoft Application (client) ID.'; return false;
      }
      this.busy = true; this.error = '';
      try {
        const result = await mailboxApi.configure(value);
        this.configuration = {login_configured:result.login_configured === true, client_id:result.client_id || '',
          template_version:result.template_version, template_label:result.template_label};
        return true;
      } catch (error) {
        this.error = error.response?.data?.detail === 'BUSY'
          ? 'Disconnect all mailboxes and cancel pending logins before changing the application ID.'
          : 'Application ID could not be saved. Check its format and backend connection.';
        return false;
      } finally { this.busy = false; }
    },
    async fetchConnections() {
      try {
        const result = await mailboxApi.list();
        this.connections = result.map(connectionView);
      } catch (error) { this.error = safeFailure(error); }
    },
    clearPrompt() {
      clearTimeout(this.pollTimer); this.pollTimer = null;
      this.prompt = null; this.loginId = null;
    },
    async cancelLogin() {
      const id = this.loginId;
      this.generation++; this.clearPrompt(); this.loginStatus = '';
      const generation = this.generation;
      if (id) {
        try { await mailboxApi.cancelLogin(id); }
        catch {
          if (generation === this.generation) {
            this.loginId = id;
            this.error = 'Login cancellation could not be confirmed. Refresh connections before starting another login.';
          }
          return false;
        }
      }
      return true;
    },
    async startLogin(accountHint = '') {
      if (this.busy) return;
      this.busy = true; this.error = '';
      const generation = this.generation + 1;
      const canceled = await this.cancelLogin();
      if (!canceled || generation !== this.generation) { this.busy = false; return; }
      try {
        const response = await mailboxApi.login(accountHint.trim() ? {account_hint:accountHint.trim()} : {});
        if (generation !== this.generation) { await mailboxApi.cancelLogin(response.login_id); return; }
        this.prompt = {login_id:response.login_id, verification_uri:response.verification_uri,
          user_code:response.user_code, expires_at:response.expires_at, interval_seconds:response.interval_seconds};
        this.loginId = response.login_id; this.loginStatus = 'PENDING';
        this.schedulePoll(generation);
      } catch (error) { if (generation === this.generation) this.error = reasons[error.response?.data?.detail]
        || 'Microsoft sign-in could not start. Check the application ID and Microsoft connection, then try again.'; }
      finally { this.busy = false; }
    },
    schedulePoll(generation) {
      if (!this.prompt || generation !== this.generation) return;
      const interval = Math.max(1, Number(this.prompt.interval_seconds) || 5) * 1000;
      this.pollTimer = setTimeout(() => this.pollLogin(generation), interval);
    },
    async pollLogin(generation) {
      const id = this.loginId;
      if (!id || generation !== this.generation) return;
      if (Date.parse(this.prompt?.expires_at) <= Date.now()) {
        await this.cancelLogin(); this.loginStatus = 'EXPIRED'; return;
      }
      try {
        const result = await mailboxApi.loginStatus(id);
        if (generation !== this.generation || this.loginId !== id) return;
        this.loginStatus = String(result.status || '').toUpperCase();
        if (this.loginStatus === 'PENDING' || this.loginStatus === 'AUTHENTICATING') this.schedulePoll(generation);
        else {
          this.clearPrompt();
          if (this.loginStatus !== 'CONNECTED') this.error = reasons[result.safe_reason]
            || 'Microsoft login did not complete. Check the application permissions and start a new login when ready.';
          await this.fetchConnections();
        }
      } catch (error) {
        if (generation !== this.generation) return;
        this.error = safeFailure(error); await this.cancelLogin();
      }
    },
    async saveMapping(id, data) {
      this.error = ''; this.busy = true;
      try { await mailboxApi.map(id, data); await this.fetchConnections(); return true; }
      catch (error) { this.error = safeFailure(error); return false; }
      finally { this.busy = false; }
    },
    async disconnect(id) {
      if (this.busy) return;
      this.error = ''; this.busy = true;
      try { await mailboxApi.disconnect(id); await this.fetchConnections(); }
      catch (error) { this.error = safeFailure(error); }
      finally { this.busy = false; }
    },
  },
});

export const useMailboxStore = defineStore('mailboxes', createMailboxStoreOptions(mailboxApi));
