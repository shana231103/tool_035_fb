// File: frontend/src/services/mailboxConnect.js
// Only request-local closures hold credentials; this module never persists them.
const reasons = Object.freeze({
  INVALID_CREDENTIAL_FORMAT: 'Enter one line: Mail|Refresh_Token|Client_id, with a valid email and application UUID.',
  CONFIGURATION_REQUIRED: 'Use the public client application ID that issued this refresh token.',
  CONSENT_REQUIRED: 'Obtain a refresh token with delegated Graph User.Read and Mail.Read consent outside this tool.',
  APP_CONSENT_REQUIRED: 'This application needs existing delegated Graph User.Read and Mail.Read consent. Obtain a new authorized refresh token outside this tool.',
  MAIL_READ_REQUIRED: 'The refresh token must authorize delegated Microsoft Graph Mail.Read.',
  GRAPH_ACCESS_DENIED: 'Microsoft Graph denied mailbox access. Check the application permissions and account support.',
  GRAPH_AUTH_REJECTED: 'Microsoft Graph rejected the token. Enter a valid refresh token for the same application.',
  MAILBOX_NOT_SUPPORTED: 'This account does not have a supported Microsoft Graph mailbox.',
  EVIDENCE_REQUIRED: 'This mail template is not supported. Use the provided Meta report template.',
  MAPPING_INVALID: 'Use the authenticated primary email. Aliases require verified delivery evidence.',
  AUTH_REQUIRED: 'The refresh token expired or was revoked. Obtain a valid token outside this tool and reconnect.',
  GRAPH_PROTOCOL_ERROR: 'Microsoft returned an unsupported response. Check the application and try a new connection.',
  MAILBOX_UNAVAILABLE: 'The mailbox is unavailable. Check the connection, then re-enter credentials to try again.',
  DISCONNECTED: 'The mailbox connection ended. Re-enter credentials to connect again.',
  BUSY: 'The mailbox is busy. Stop its active report before changing the connection.',
  THROTTLED: 'Microsoft is limiting requests. Wait before re-entering credentials.',
});
export const mailboxReason = error => {
  const value = error?.response?.data?.detail ?? error?.message;
  return Object.hasOwn(reasons, value) ? value : 'MAILBOX_UNAVAILABLE';
};
export const mailboxMessage = reason => reasons[reason] || reasons.MAILBOX_UNAVAILABLE;
export const connectionView = item => ({
  id: item.id, status: ['pending', 'connected', 'reauth_required', 'error', 'disconnecting'].includes(item.status) ? item.status : 'error',
  masked_email: item.masked_email, mapped_email_masked: item.mapped_email_masked,
  expires_at: item.expires_at, safe_reason: Object.hasOwn(reasons, item.safe_reason) ? item.safe_reason : null,
});
export function validMailboxCredentials(value) {
  if (typeof value !== 'string' || new TextEncoder().encode(value).length > 16384 || /[\x00-\x1f\x7f]/.test(value)) return false;
  const parts = value.split('|').map(part => part.trim());
  if (parts.length !== 3 || parts.some(part => !part)) return false;
  return parts[0].length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(parts[0]) && !/\s/.test(parts[1])
    && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(parts[2]);
}

export function createMailboxConnectSession(api, store) {
  const attempts = new Set();
  async function cleanup(id) {
    store.requireCleanup(id);
    try { await api.disconnect(id); store.confirmCleanup(id); return true; }
    catch { store.cleanupFailed(); return false; }
  }
  async function submit(input) {
    let credentials = input?.value || '';
    if (input) input.value = ''; // Synchronous, before validation or any await.
    if (!validMailboxCredentials(credentials)) { credentials = ''; store.invalidCredentials(); return false; }
    const generation = store.beginConnect();
    if (generation === null) { credentials = ''; return false; }
    const controller = new AbortController();
    const attempt = {id: null, cancel: () => { credentials = ''; controller.abort(); }};
    attempts.add(attempt);
    try {
      // Do not abort reservation: drain its late response to delete the empty record.
      const reservation = await api.reserve();
      attempt.id = reservation.id;
      if (!store.isCurrent(generation)) { credentials = ''; await cleanup(attempt.id); return false; }
      store.reserved(generation, attempt.id);
      const connecting = api.connect(attempt.id, credentials, controller.signal);
      credentials = '';
      const result = await connecting;
      if (!store.isCurrent(generation)) { await cleanup(attempt.id); return false; }
      store.connected(generation, connectionView(result));
      return true;
    } catch (error) {
      credentials = '';
      const reason = mailboxReason(error);
      if (attempt.id) await cleanup(attempt.id);
      store.connectFailed(generation, reason);
      return false;
    } finally { credentials = ''; attempts.delete(attempt); store.finishConnect(generation); }
  }
  async function close(input) {
    if (input) input.value = '';
    store.closePanel();
    const pending = [];
    for (const attempt of attempts) {
      attempt.cancel();
      if (attempt.id) pending.push(cleanup(attempt.id));
    }
    await Promise.all(pending);
  }
  return {submit, close};
}
