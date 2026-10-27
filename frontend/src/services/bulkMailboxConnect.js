// File: frontend/src/services/bulkMailboxConnect.js
import { validMailboxCredentials, mailboxReason } from './mailboxConnect.js';
import { maskEmail, normalizeBulkText } from '../utils/bulkOrderFile.js';

// Credentials and exact emails exist only inside this request-owned service closure.
export function createBulkMailboxSession(api, publish = () => {}) {
  let epoch = 0, active = null, refs = [], publicRows = [];
  const owned = new Set(), cleanupIds = new Set(), cleanups = new Map(), cache = new Map(), controllers = new Set();
  const emit = () => publish(publicRows.map(row => ({...row})), [...cleanupIds]);
  async function cleanup(id) {
    if (!owned.has(id)) return;
    if (cleanups.has(id)) return cleanups.get(id);
    cleanupIds.add(id);
    const work = (async () => {
      try { await api.disconnect(id); cleanupIds.delete(id); owned.delete(id); }
      catch { /* Retain owned IDs for explicit cleanup retry. */ }
      finally { cleanups.delete(id); emit(); }
    })();
    cleanups.set(id, work); return work;
  }
  async function cancel() {
    epoch++;
    for (const controller of controllers) controller.abort();
    refs = [];
    await Promise.all([...owned].map(cleanup));
    if (active) await active;
    await Promise.all([...owned].filter(id => !cleanupIds.has(id)).map(cleanup));
  }
  async function connect(text) {
    await cancel();
    if (cleanupIds.size) throw new Error('Cần xác nhận dọn kết nối trước khi nhập lại.');
    const generation = ++epoch;
    let lines;
    try { lines = normalizeBulkText(text).split('\n'); } finally { text = ''; }
    const queue = [], seen = new Set();
    publicRows = []; refs = [];
    for (const [index, raw] of lines.entries()) {
      const credentials = raw.trim();
      if (!credentials) continue;
      const email = credentials.split('|', 1)[0].trim().toLowerCase();
      const row = {source_line:index + 1, masked_email:maskEmail(email), status:'pending', reason:null};
      publicRows.push(row);
      if (!validMailboxCredentials(credentials)) { row.status = 'excluded'; row.reason = 'INVALID_CREDENTIAL_FORMAT'; }
      else if (seen.has(email)) { row.status = 'excluded'; row.reason = 'DUPLICATE_MAILBOX'; }
      else { seen.add(email); queue.push({row, credentials, email}); }
    }
    lines.fill(''); lines = null;
    if (publicRows.length > 100) {
      queue.forEach(item => {item.credentials = '';});
      publicRows = [{source_line:1, masked_email:'***', status:'excluded', reason:'IMPORT_LIMIT_EXCEEDED'}];
      emit(); return publicRows.map(row => ({...row}));
    }
    emit();
    let cursor = 0;
    const ready = [];
    async function worker() {
      while (generation === epoch && cursor < queue.length) {
        const item = queue[cursor++];
        let id = null;
        const controller = new AbortController(); controllers.add(controller);
        try {
          // Only service-known exact identities may be reused, never masked-email guesses.
          const known = cache.get(item.email);
          if (known && (await api.list()).some(row => row.id === known && row.status === 'connected')) {
            item.credentials = '';
            if (generation !== epoch) continue;
            ready.push({source_line:item.row.source_line, expected_email:item.email, connection_id:known});
            item.row.status = 'ready'; continue;
          }
          const reservation = await api.reserve(); id = reservation.id; owned.add(id);
          if (generation !== epoch) { item.credentials = ''; await cleanup(id); continue; }
          item.row.status = 'connecting'; emit();
          const request = api.connect(id, item.credentials, controller.signal); item.credentials = '';
          const result = await request;
          if (generation !== epoch) { await cleanup(id); continue; }
          if (result.status !== 'connected' || result.id !== id) throw new Error('MAILBOX_UNAVAILABLE');
          cache.set(item.email, id);
          ready.push({source_line:item.row.source_line, expected_email:item.email, connection_id:id});
          item.row.status = 'ready';
        } catch (error) {
          item.credentials = '';
          if (id) await cleanup(id);
          if (generation === epoch) { item.row.status = 'excluded'; item.row.reason = mailboxReason(error); }
        } finally { item.credentials = ''; controllers.delete(controller); if (generation === epoch) emit(); }
      }
    }
    const work = Promise.all([worker(), worker()]); active = work;
    try { await work; }
    finally { queue.forEach(item => {item.credentials = '';}); if (active === work) active = null; }
    if (generation === epoch) { refs = ready.sort((a,b) => a.source_line - b.source_line); emit(); }
    return publicRows.map(row => ({...row}));
  }
  return {
    connect, cancel,
    references: () => refs.map(row => ({...row})),
    handoff() { for (const ref of refs) owned.delete(ref.connection_id); },
    async retryCleanup() { await Promise.all([...cleanupIds].map(cleanup)); return cleanupIds.size === 0; },
  };
}
