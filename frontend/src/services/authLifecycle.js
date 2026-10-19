// File: frontend/src/services/authLifecycle.js
import { authApi } from "./auth.js";
import { useAuthStore } from "../stores/authStore.js";
import { wsService } from "./websocket.js";

class AuthLifecycle {
  constructor() {
    this._epoch = 0;
    this._storeHooks = [];
    this._channel = null;
    this._router = null;
    this._initBroadcastChannel();
    this._initVisibilityListener();
  }

  setRouter(router) {
    this._router = router;
  }

  get currentEpoch() {
    return this._epoch;
  }

  registerStoreHook(hook) {
    if (hook && (hook.resetForAuth || hook.stop)) {
      this._storeHooks.push(hook);
    }
  }

  beginTransition(reason = "transition") {
    this._epoch += 1;
    const authStore = useAuthStore();
    authStore.setTransitioning();
    return this._epoch;
  }

  async teardown(epoch) {
    wsService.disconnect();
    for (const hook of this._storeHooks) {
      try {
        if (hook.stop) {
          await hook.stop();
        }
        if (hook.resetForAuth) {
          hook.resetForAuth(epoch);
        }
      } catch (err) {
        console.error("Error tearing down store for auth:", err);
      }
    }
  }

  async bootstrap() {
    const authStore = useAuthStore();
    authStore.setChecking();
    const epoch = this._epoch;

    try {
      const view = await authApi.session();
      if (epoch !== this._epoch) return authStore.status;
      if (view && view.authenticated) {
        this.acceptSession(view, epoch);
      } else {
        authStore.clearSession();
      }
    } catch (err) {
      if (epoch !== this._epoch) return authStore.status;
      if (err.response?.status === 503 || !err.response) {
        authStore.setUnavailable();
      } else {
        authStore.clearSession();
      }
    }
    return authStore.status;
  }

  acceptSession(view, epoch) {
    if (epoch !== undefined && epoch !== this._epoch) return;
    const authStore = useAuthStore();
    authStore.setSession(view);
    wsService.connect();
    this._postSessionChanged();
  }

  async login(username, password) {
    const authStore = useAuthStore();
    authStore.setChecking();
    const epoch = this.beginTransition("login");
    await this.teardown(epoch);

    try {
      const view = await authApi.login({ username, password });
      this.acceptSession(view, epoch);
      if (this._router) {
        await this._router.push("/");
      }
      return view;
    } catch (err) {
      authStore.clearSession();
      throw err;
    }
  }

  async logout() {
    const authStore = useAuthStore();
    const csrfToken = authStore.csrfToken;
    const sessionContext = authStore.sessionContext;
    const epoch = this.beginTransition("logout");
    await this.teardown(epoch);

    try {
      await authApi.logout({ csrfToken, sessionContext });
    } catch (err) {
      // Failed or expired logout still concludes guest transition locally
    } finally {
      authStore.clearSession();
      this._postSessionChanged();
      if (this._router) {
        await this._router.push("/login");
      }
    }
  }

  async handleAuthLoss(error, epoch) {
    if (epoch !== undefined && epoch !== this._epoch) return;
    const transitionEpoch = this.beginTransition("auth_loss");
    await this.teardown(transitionEpoch);
    const authStore = useAuthStore();
    authStore.clearSession();
    this._postSessionChanged();
    if (this._router && this._router.currentRoute.value.path !== "/login") {
      await this._router.push("/login");
    }
  }

  async recheckOnVisibility() {
    if (typeof document !== "undefined" && document.visibilityState === "visible") {
      const authStore = useAuthStore();
      if (authStore.isAuthenticated) {
        try {
          const view = await authApi.session();
          if (!view || !view.authenticated) {
            await this.handleAuthLoss(new Error("Session expired on restore"));
          } else {
            authStore.setSession(view);
          }
        } catch (err) {
          // ignore transient error
        }
      }
    }
  }

  _initBroadcastChannel() {
    if (typeof window !== "undefined" && window.BroadcastChannel) {
      this._channel = new window.BroadcastChannel("operator_session");
      this._channel.onmessage = async (event) => {
        if (event.data?.type === "SESSION_CHANGED") {
          const epoch = this.beginTransition("multitab_sync");
          await this.teardown(epoch);
          await this.bootstrap();
        }
      };
    }
  }

  _postSessionChanged() {
    if (this._channel) {
      this._channel.postMessage({ type: "SESSION_CHANGED", nonce: Math.random() });
    }
  }

  _initVisibilityListener() {
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", () => {
        this.recheckOnVisibility();
      });
    }
  }
}

export const authLifecycle = new AuthLifecycle();
