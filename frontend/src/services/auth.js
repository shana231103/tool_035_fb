// File: frontend/src/services/auth.js
import axios from "axios";
import { withAuthMutationLock } from "./authMutationLock.js";

const authClient = axios.create({
  baseURL: "/api/v1/auth",
  timeout: 15000,
  headers: {
    "Content-Type": "application/json",
  },
});

export const authApi = {
  async session(options = {}) {
    const res = await authClient.get("/session", {
      signal: options.signal,
    });
    return res.data;
  },

  async login({ username, password }, options = {}) {
    return await withAuthMutationLock(async () => {
      const res = await authClient.post(
        "/login",
        { username, password },
        {
          headers: {
            "X-Operator-Login": "1",
          },
          signal: options.signal,
        }
      );
      return res.data;
    });
  },

  async logout(options = {}) {
    return await withAuthMutationLock(async () => {
      const headers = {};
      if (options.csrfToken) {
        headers["X-CSRF-Token"] = options.csrfToken;
      }
      if (options.sessionContext) {
        headers["X-Operator-Session"] = options.sessionContext;
      }
      await authClient.post("/logout", {}, { headers, signal: options.signal });
    });
  },
};
