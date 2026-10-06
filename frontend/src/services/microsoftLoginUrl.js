// Microsoft-generated device URL; this does not accept arbitrary sign-in redirects.
export function microsoftLoginUrl(value) {
  try {
    const url = new URL(value);
    const hosts = ['microsoft.com', 'www.microsoft.com', 'login.microsoftonline.com', 'login.live.com', 'login.microsoft.com'];
    if (url.protocol !== 'https:' || !hosts.includes(url.hostname) || url.username || url.password ||
        (url.port && url.port !== '443')) return '';
    if (url.hostname === 'login.microsoft.com' &&
        (url.pathname !== '/device' || url.search || url.hash)) return '';
    return url.href;
  } catch { return ''; }
}
