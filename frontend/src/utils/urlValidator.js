/**
 * URL Validation & Account Extraction Utility for Meta Platforms
 * Supports: Facebook, Instagram, Threads
 * Validates against localhost/private IPs for DMCA compliance
 */

/**
 * Helper to safely parse any URL string (with or without protocol) using standard WHATWG URL.
 * @param {string} urlString
 * @returns {URL | null}
 */
export function getParsedUrl(urlString) {
  if (!urlString || typeof urlString !== "string") return null;
  const str = urlString.trim();
  if (!str) return null;
  try {
    const withScheme =
      str.startsWith("http://") || str.startsWith("https://")
        ? str
        : `https://${str}`;
    return new URL(withScheme);
  } catch {
    return null;
  }
}

/**
 * Checks if a URL or host points to localhost, loopback, or private internal IP ranges.
 * Parses the URL hostname first and validates strictly against the parsed hostname.
 * @param {string} urlString
 * @returns {boolean}
 */
export function isLocalhostOrPrivateUrl(urlString) {
  const parsed = getParsedUrl(urlString);
  if (!parsed) return false;

  let hostname = parsed.hostname.toLowerCase();
  // Strip brackets from IPv6 hostnames like "[::1]"
  if (hostname.startsWith("[") && hostname.endsWith("]")) {
    hostname = hostname.slice(1, -1);
  }

  // Named hosts and local domain suffixes
  if (
    hostname === "localhost" ||
    hostname.endsWith(".localhost") ||
    hostname === "local" ||
    hostname.endsWith(".local") ||
    hostname === "internal" ||
    hostname.endsWith(".internal") ||
    hostname === "127.0.0.1" ||
    hostname === "0.0.0.0" ||
    hostname === "::1" ||
    hostname === "0:0:0:0:0:0:0:1"
  ) {
    return true;
  }

  // IPv6 loopback / unique local / link-local / unspecified
  if (
    hostname === "::" ||
    hostname.startsWith("fe80:") ||
    hostname.startsWith("fd") ||
    hostname.startsWith("fc")
  ) {
    return true;
  }

  // IPv4 ranges:
  // 127.0.0.0/8 (Loopback)
  // 10.0.0.0/8 (RFC 1918)
  // 172.16.0.0/12 (RFC 1918: 172.16.0.0 - 172.31.255.255)
  // 192.168.0.0/16 (RFC 1918)
  // 169.254.0.0/16 (Link-local RFC 3927)
  const ipv4Match = hostname.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (ipv4Match) {
    const o1 = parseInt(ipv4Match[1], 10);
    const o2 = parseInt(ipv4Match[2], 10);
    const o3 = parseInt(ipv4Match[3], 10);
    const o4 = parseInt(ipv4Match[4], 10);

    if (o1 > 255 || o2 > 255 || o3 > 255 || o4 > 255) return false;
    if (o1 === 127 || o1 === 0) return true; // loopback & default
    if (o1 === 10) return true; // 10.0.0.0/8
    if (o1 === 172 && o2 >= 16 && o2 <= 31) return true; // 172.16.0.0/12
    if (o1 === 192 && o2 === 168) return true; // 192.168.0.0/16
    if (o1 === 169 && o2 === 254) return true; // 169.254.0.0/16
  }

  return false;
}

/**
 * Validates that a URL is a publicly accessible URL and not localhost.
 * @param {string} urlString
 * @returns {{ valid: boolean, error?: string }}
 */
export function validateOriginalWorkUrl(urlString) {
  if (!urlString || typeof urlString !== "string" || !urlString.trim()) {
    return { valid: false, error: "Original work URL cannot be empty." };
  }

  const clean = urlString.trim();

  if (isLocalhostOrPrivateUrl(clean)) {
    return {
      valid: false,
      error:
        "Localhost or private IP URLs cannot be accessed by Meta reviewers. Please provide a publicly accessible URL.",
    };
  }

  const parsed = getParsedUrl(clean);
  if (!parsed || !parsed.hostname || !parsed.hostname.includes(".")) {
    return { valid: false, error: "Invalid public domain name." };
  }

  return { valid: true };
}

const FB_DOMAINS = ["facebook.com", "fb.watch", "fb.com"];
const IG_DOMAINS = ["instagram.com", "instagr.am"];
const THREADS_DOMAINS = ["threads.net", "threads.com"];
const ALL_META_DOMAINS = [...FB_DOMAINS, ...IG_DOMAINS, ...THREADS_DOMAINS];

function hostMatchesFamily(hostname, domains) {
  if (!hostname) return false;
  return domains.some(
    (base) => hostname === base || hostname.endsWith(`.${base}`)
  );
}

/**
 * Validates that a URL points to a Meta platform (Facebook, Instagram, Threads).
 * Uses WHATWG URL parsing and strict hostname whitelist validation.
 * @param {string} urlString
 * @returns {boolean}
 */
export function isValidMetaUrl(urlString) {
  const parsed = getParsedUrl(urlString);
  if (!parsed) return false;
  const hostname = parsed.hostname.toLowerCase();
  return hostMatchesFamily(hostname, ALL_META_DOMAINS);
}

/**
 * Detects the Meta platform of a given URL.
 * @param {string} urlString
 * @returns {"FACEBOOK" | "INSTAGRAM" | "THREADS" | "UNKNOWN"}
 */
export function detectPlatform(urlString) {
  const parsed = getParsedUrl(urlString);
  if (!parsed) return "UNKNOWN";
  const hostname = parsed.hostname.toLowerCase();

  if (hostMatchesFamily(hostname, FB_DOMAINS)) {
    return "FACEBOOK";
  }
  if (hostMatchesFamily(hostname, IG_DOMAINS)) {
    return "INSTAGRAM";
  }
  if (hostMatchesFamily(hostname, THREADS_DOMAINS)) {
    return "THREADS";
  }
  return "UNKNOWN";
}

/**
 * Detects content type (photo, video, reel, story, post, media) from URL structure.
 * @param {string} urlString
 * @returns {"photo" | "video" | "reel" | "story" | "post" | "media"}
 */
export function detectContentType(urlString) {
  const parsed = getParsedUrl(urlString);
  if (!parsed) return "post";
  const hostname = parsed.hostname.toLowerCase();
  const path = parsed.pathname.toLowerCase();
  const search = parsed.search.toLowerCase();
  const combined = path + search;

  if (hostMatchesFamily(hostname, FB_DOMAINS)) {
    if (
      combined.includes("/photo") ||
      combined.includes("fbid=") ||
      combined.includes("/photos")
    ) {
      return "photo";
    }
    if (
      combined.includes("/reel") ||
      combined.includes("/watch") ||
      hostname === "fb.watch" ||
      hostname.endsWith(".fb.watch") ||
      combined.includes("/videos")
    ) {
      return "video";
    }
    return "post";
  }

  if (hostMatchesFamily(hostname, IG_DOMAINS)) {
    if (path.includes("/reel/")) return "reel";
    if (path.includes("/p/")) return "post";
    if (path.includes("/stories/")) return "story";
    return "media";
  }

  if (hostMatchesFamily(hostname, THREADS_DOMAINS)) {
    return "post";
  }

  return "post";
}

const IG_RESERVED = new Set([
  "reel",
  "reels",
  "p",
  "stories",
  "explore",
  "direct",
  "tv",
  "share",
  "accounts",
  "developer",
  "about",
  "legal",
  "login",
  "emails",
]);

const FB_RESERVED = new Set([
  "watch",
  "reel",
  "reels",
  "share",
  "photo",
  "photos",
  "photo.php",
  "video",
  "videos",
  "video.php",
  "story.php",
  "permalink.php",
  "media",
  "events",
  "marketplace",
  "gaming",
  "help",
  "login",
  "checkpoint",
  "recover",
  "home",
  "home.php",
  "messages",
  "groups",
  "pages",
  "profile.php",
  "live",
  "saved",
  "settings",
]);

/**
 * Extracts the infringing account handle or channel identifier from Meta URLs.
 * @param {string} urlString
 * @returns {string | null} e.g. "@username" or "id=12345" or null if unparseable
 */
export function extractAccountHandle(urlString) {
  const parsed = getParsedUrl(urlString);
  if (!parsed) return null;

  const hostname = parsed.hostname.toLowerCase();
  const pathname = parsed.pathname;

  // 1. Threads extraction: threads.net/@username or threads.com/@username
  if (hostMatchesFamily(hostname, THREADS_DOMAINS)) {
    const threadsMatch = pathname.match(/@([a-zA-Z0-9._]+)/);
    if (threadsMatch && threadsMatch[1]) {
      return `@${threadsMatch[1]}`;
    }
  }

  // 2. Instagram extraction
  if (hostMatchesFamily(hostname, IG_DOMAINS)) {
    // Format: /stories/username/12345/
    const storiesMatch = pathname.match(/^\/stories\/([a-zA-Z0-9._]+)/i);
    if (storiesMatch && storiesMatch[1] && !IG_RESERVED.has(storiesMatch[1].toLowerCase())) {
      return `@${storiesMatch[1]}`;
    }

    // Format: /username/p/123/ or /username/reel/123/ or /username/
    const segments = pathname.split("/").filter((s) => s.length > 0);
    if (segments.length > 0) {
      const first = segments[0].replace(/^@/, "");
      if (!IG_RESERVED.has(first.toLowerCase()) && /^[a-zA-Z0-9._]+$/.test(first)) {
        return `@${first}`;
      }
    }
  }

  // 3. Facebook extraction
  if (hostMatchesFamily(hostname, FB_DOMAINS)) {
    // Format: profile.php?id=12345678, permalink.php?id=..., story.php?id=...
    const idParam = parsed.searchParams.get("id");
    if (idParam && /^\d+$/.test(idParam)) {
      return `id=${idParam}`;
    }

    // Path segments: facebook.com/username/posts/... or facebook.com/username
    const segments = pathname.split("/").filter((s) => s.length > 0);
    if (segments.length > 0) {
      // Skip prefix like 'people' or 'pages' or 'pg'
      let candidate = segments[0];
      if (
        (candidate === "people" || candidate === "pages" || candidate === "pg") &&
        segments.length > 1
      ) {
        candidate = segments[1];
      }

      const cleanCandidate = candidate.replace(/^@/, "");
      if (
        !FB_RESERVED.has(cleanCandidate.toLowerCase()) &&
        /^[a-zA-Z0-9._-]+$/.test(cleanCandidate)
      ) {
        return `@${cleanCandidate}`;
      }
    }
  }

  return null;
}

/**
 * Parses a single raw target URL into a rich descriptor.
 * @param {string} rawUrl
 * @returns {{
 *   url: string,
 *   platform: "FACEBOOK" | "INSTAGRAM" | "THREADS" | "UNKNOWN",
 *   contentType: string,
 *   account: string | null,
 *   isValidMeta: boolean,
 *   error?: string
 * }}
 */
export function parseTargetUrl(rawUrl) {
  const clean = (rawUrl || "").trim();
  if (!clean) {
    return {
      url: "",
      platform: "UNKNOWN",
      contentType: "post",
      account: null,
      isValidMeta: false,
      error: "URL is empty",
    };
  }

  const isValid = isValidMetaUrl(clean);
  const platform = detectPlatform(clean);
  const contentType = detectContentType(clean);
  const account = extractAccountHandle(clean);

  // Normalize scheme
  const normalizedUrl =
    clean.startsWith("http://") || clean.startsWith("https://")
      ? clean
      : `https://${clean}`;

  return {
    url: normalizedUrl,
    platform,
    contentType,
    account,
    isValidMeta: isValid,
    error: isValid ? undefined : "URL is not a recognized Meta platform link (Facebook, Instagram, Threads)",
  };
}

/**
 * Parses multiline raw text containing one URL per line.
 * @param {string} text
 * @returns {{
 *   all: Array<ReturnType<typeof parseTargetUrl>>,
 *   valid: Array<ReturnType<typeof parseTargetUrl>>,
 *   invalid: Array<ReturnType<typeof parseTargetUrl>>,
 *   hasNonMeta: boolean
 * }}
 */
export function parseBatchUrls(text) {
  if (!text || typeof text !== "string") {
    return { all: [], valid: [], invalid: [], hasNonMeta: false };
  }

  const lines = text
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 0);

  const all = lines.map(parseTargetUrl);
  const valid = all.filter((item) => item.isValidMeta);
  const invalid = all.filter((item) => !item.isValidMeta);

  return {
    all,
    valid,
    invalid,
    hasNonMeta: invalid.length > 0,
  };
}


// Facebook restriction applies to this workflow; parsers remain available for historical records.
export function parseFacebookBatchUrls(text) {
  const result = parseBatchUrls(text);
  const valid = result.all.filter(item => item.isValidMeta && item.platform === 'FACEBOOK');
  const invalid = result.all.filter(item => !item.isValidMeta || item.platform !== 'FACEBOOK');
  return {all:result.all, valid, invalid, hasNonMeta:invalid.length > 0};
}
