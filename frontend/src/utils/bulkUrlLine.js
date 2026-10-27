// File: frontend/src/utils/bulkUrlLine.js
const EDGE_WHITESPACE = new Set('\t\n\v\f\r \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000');
export function trimBulkLine(value) {
  let start = 0, end = value.length;
  while (start < end && EDGE_WHITESPACE.has(value[start])) start++;
  while (end > start && EDGE_WHITESPACE.has(value[end - 1])) end--;
  return value.slice(start, end);
}

function validAuthority(authority) {
  if (/[@%\\<>^`{}"=,;|]/u.test(authority)) return false;
  const match = authority.startsWith('[')
    ? authority.match(/^\[([^\]]+)\](?::([0-9]+))?$/u)
    : authority.match(/^([^:]+)(?::([0-9]+))?$/u);
  if (!match) return false;
  const port = match[2]?.replace(/^0+/u, '') || '0';
  if (port.length > 5 || Number(port) > 65535) return false;
  try {
    const parsed = new URL(`https://${authority}`);
    if (authority.startsWith('[')) return match[1].includes(':') && parsed.hostname.startsWith('[');
    const host = parsed.hostname.replace(/\.$/u, '');
    return host.length <= 253 && host.split('.').every(label => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/iu.test(label));
  } catch { return false; }
}

function looksLikeUrlStart(value, start) {
  if (/^(?:https?:\/\/|\/\/)/iu.test(value.slice(start, start + 8))) return true;
  const token = /[^/\?#,;|]{0,301}/uy;
  token.lastIndex = start;
  const authority = token.exec(value)[0];
  if (authority.length > 300) return false;
  const host = authority.split(':', 1)[0];
  const ipv4 = /^[0-9]+(?:\.[0-9]+){3}$/u.test(host) && host.split('.').every(part => /^(?:0|[1-9][0-9]*)$/u.test(part) && Number(part) <= 255);
  const qualified = host.includes('.') && /\p{L}/u.test(host);
  return (qualified || ipv4) && validAuthority(authority);
}

export function validateBulkUrlLine(value) {
  if (typeof value !== 'string' || /\p{Cf}/u.test(value)) return false;
  const clean = trimBulkLine(value);
  if (!clean || /[\p{White_Space}\p{Cc}\p{Cf}\\]/u.test(clean) || clean.startsWith('//')) return false;
  for (const match of clean.matchAll(/[,;|]/gu)) {
    if (looksLikeUrlStart(clean, match.index + 1)) return false;
  }
  const scheme = clean.match(/^([a-z][a-z0-9+.-]*):/iu);
  if (scheme && !scheme[1].includes('.') && !/^https?$/iu.test(scheme[1])) return false;
  const candidate = /^https?:\/\//iu.test(clean) ? clean : `https://${clean}`;
  try {
    const authority = candidate.slice(candidate.indexOf('://') + 3).split(/[/\?#]/u, 1)[0];
    const parsed = new URL(candidate);
    return ['http:', 'https:'].includes(parsed.protocol) && !!parsed.hostname && validAuthority(authority);
  } catch { return false; }
}
