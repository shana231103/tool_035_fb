// File: frontend/src/utils/bulkOrderFile.js
import { detectPlatform, validateOriginalWorkUrl } from './urlValidator.js';
import { trimBulkLine, validateBulkUrlLine } from './bulkUrlLine.js';
export const BULK_FILE_LIMIT = 2097152;
export const maskEmail = value => {
  const [name, host] = String(value).split('@');
  return host ? `${name.slice(0, 1)}***@${host}` : '***';
};
export function normalizeBulkText(text) {
  if (typeof text !== 'string' || new TextEncoder().encode(text).length > BULK_FILE_LIMIT) throw new Error('IMPORT_LIMIT_EXCEEDED');
  return text.replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n');
}
export async function readBulkFile(file) {
  if (!file || file.size > BULK_FILE_LIMIT || !/\.txt$/i.test(file.name)) throw new Error('Chọn tệp TXT UTF-8 tối đa 2 MiB.');
  try {
    const text = new TextDecoder('utf-8', {fatal:true, ignoreBOM:true}).decode(await file.arrayBuffer());
    normalizeBulkText(text);
    return text;
  }
  catch { throw new Error('Không đọc được TXT UTF-8 hoặc tệp vượt 2 MiB.'); }
}
export function parseBulkOrders(input) {
  const errors = [], orders = [], seen = new Set();
  let text;
  try { text = normalizeBulkText(input); } catch { return {orders, errors:[{source_line:1, reason:'IMPORT_LIMIT_EXCEEDED'}]}; }
  let current = null, stage = null, blocks = 0;
  const finish = () => {
    if (!current) return;
    if (!current.original_url || stage !== 'targets' || !current.target_urls.length) errors.push({source_line:current.source_line, reason:'ORDER_FORMAT_INVALID'});
    else if (current.target_urls.length > 30) errors.push({source_line:current.source_line, reason:'TOO_MANY_TARGETS'});
    else {
      const identity = JSON.stringify([current.original_url, current.target_urls]);
      if (seen.has(identity)) errors.push({source_line:current.source_line, reason:'DUPLICATE_ORDER'});
      seen.add(identity); orders.push({...current, sequence:orders.length + 1});
    }
  };
  for (const [index, raw] of text.split('\n').entries()) {
    const source_line = index + 1;
    if (raw.includes('\uFEFF')) { errors.push({source_line, reason:'ORDER_FORMAT_INVALID'}); continue; }
    const value = trimBulkLine(raw);
    if (!value) continue;
    const label = value.toLocaleLowerCase('vi');
    if (label === 'tên website') {
      finish(); blocks++;
      if (blocks > 1000) { errors.push({source_line, reason:'IMPORT_LIMIT_EXCEEDED'}); current = null; break; }
      current = {source_line, original_url:null, target_urls:[]}; stage = 'original'; continue;
    }
    if (label === 'website đã fake bài') {
      if (stage === 'label') stage = 'targets';
      else errors.push({source_line, reason:'ORDER_FORMAT_INVALID'});
      continue;
    }
    if (stage === 'original' || stage === 'targets') {
      if (!validateBulkUrlLine(raw)) { errors.push({source_line, reason:'ORDER_URL_INVALID'}); continue; }
      let url;
      try { url = new URL(/^https?:\/\//i.test(value) ? value : `https://${value}`); } catch { url = null; }
      const publicHttp = url && ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password && value.length <= 2048;
      if (!publicHttp || (stage === 'original' ? !validateOriginalWorkUrl(url.href).valid : detectPlatform(url.href) !== 'FACEBOOK')) {
        errors.push({source_line, reason:'ORDER_URL_INVALID'}); continue;
      }
      if (stage === 'original') { current.original_url = url.href; stage = 'label'; }
      else current.target_urls.push(url.href);
    } else errors.push({source_line, reason:'ORDER_FORMAT_INVALID'});
  }
  finish();
  if (!orders.length && !errors.length) errors.push({source_line:1, reason:'ORDER_FORMAT_INVALID'});
  return {orders, errors};
}
