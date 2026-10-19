// File: frontend/src/services/authMutationLock.js
/**
 * Cross-tab cookie-mutation exclusion using Web Locks API when available.
 * Guarantees only one tab executes credential/cookie-changing requests at a time.
 */
let localLockPromise = Promise.resolve();

export async function withAuthMutationLock(fn) {
  if (typeof navigator !== "undefined" && navigator.locks && navigator.locks.request) {
    try {
      return await navigator.locks.request("meta_reporter_auth_mutation", { mode: "exclusive" }, async () => {
        return await fn();
      });
    } catch (e) {
      // If Web Locks fails unexpectedly, fall through to in-process single-flight lock
      console.warn("navigator.locks request failed, falling back to local lock:", e);
    }
  }

  // Fallback: in-process sequential lock
  const prev = localLockPromise;
  let release;
  localLockPromise = new Promise((resolve) => {
    release = resolve;
  });

  try {
    await prev;
    return await fn();
  } finally {
    release();
  }
}
