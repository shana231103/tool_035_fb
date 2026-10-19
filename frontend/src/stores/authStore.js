// File: frontend/src/stores/authStore.js
import { defineStore } from "pinia";
import { ref, computed } from "vue";

export const useAuthStore = defineStore("auth", () => {
  const status = ref("unknown"); // unknown | checking | authenticated | guest | unavailable | transitioning
  const operator = ref(null); // { id, username }
  const sessionContext = ref(null); // UUID string
  const csrfToken = ref(null);
  const expiresAt = ref(null);
  const idleExpiresAt = ref(null);

  const isAuthenticated = computed(() => status.value === "authenticated");
  const isChecking = computed(() => status.value === "checking" || status.value === "unknown");
  const isGuest = computed(() => status.value === "guest");
  const isUnavailable = computed(() => status.value === "unavailable");

  function setChecking() {
    status.value = "checking";
  }

  function setSession(view) {
    if (view && view.authenticated && view.operator) {
      status.value = "authenticated";
      operator.value = view.operator;
      sessionContext.value = view.session_context;
      csrfToken.value = view.csrf_token;
      expiresAt.value = view.expires_at;
      idleExpiresAt.value = view.idle_expires_at;
    } else {
      clearSession();
    }
  }

  function clearSession() {
    status.value = "guest";
    operator.value = null;
    sessionContext.value = null;
    csrfToken.value = null;
    expiresAt.value = null;
    idleExpiresAt.value = null;
  }

  function setUnavailable() {
    status.value = "unavailable";
    operator.value = null;
    sessionContext.value = null;
    csrfToken.value = null;
  }

  function setTransitioning() {
    status.value = "transitioning";
  }

  return {
    status,
    operator,
    sessionContext,
    csrfToken,
    expiresAt,
    idleExpiresAt,
    isAuthenticated,
    isChecking,
    isGuest,
    isUnavailable,
    setChecking,
    setSession,
    clearSession,
    setUnavailable,
    setTransitioning,
  };
});
